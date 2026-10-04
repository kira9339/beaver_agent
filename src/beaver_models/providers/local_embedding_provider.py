"""Local embedding provider backed by sentence-transformers models.

Loads a sentence-transformers model directly from the local HuggingFace hub
cache, so no API key or network access is required. The multi-GB model is
loaded lazily on first use, so commands that do not need embeddings (e.g.
``beaver version``) are not slowed down by model loading.
"""

import asyncio
import os
import threading
from typing import Dict, Optional, Any
from pathlib import Path

import numpy as np

from ..base import EmbeddingConfig, ModelAPIError


class LocalEmbeddingProvider:
    """Embedding provider that runs a local sentence-transformers model."""

    def __init__(
        self,
        config: EmbeddingConfig,
        model_path: Optional[str] = None,
        device: Optional[str] = None,
    ):
        """
        Args:
            config: Embedding model configuration.
            model_path: Local model location. Accepts either the HuggingFace
                hub cache directory (the folder that contains ``models--*``,
                e.g. ``D:/hf_cache/hub``), a ``models--*`` model directory, or
                a directory pointing directly at a sentence-transformers model.
                If None, falls back to ``HF_HUB_CACHE`` / ``HF_HOME`` env vars
                or the default ``~/.cache/huggingface/hub``.
            device: torch device, e.g. ``"cpu"`` or ``"cuda"``. Defaults to
                ``cuda`` when available, otherwise ``cpu``.
        """
        self.config = config
        self.model_path = model_path
        self.device = device
        self._model = None
        self._is_initialized = False
        # Model loading runs on a worker thread and may be requested by several
        # requests at once (startup warm-up racing the first upload).
        self._load_lock = threading.Lock()

    async def initialize(self) -> None:
        """Mark the provider initialized. The model itself loads lazily."""
        self._is_initialized = True

    def _default_cache_dir(self) -> str:
        """Resolve the default HuggingFace hub cache directory."""
        if os.environ.get("HF_HUB_CACHE"):
            return os.environ["HF_HUB_CACHE"]
        if os.environ.get("HF_HOME"):
            return os.path.join(os.environ["HF_HOME"], "hub")
        return str(Path.home() / ".cache" / "huggingface" / "hub")

    def _pick_snapshot(self, model_dir: Path) -> Optional[Path]:
        """Choose a usable snapshot under a ``models--*`` cache directory."""
        snapshots_dir = model_dir / "snapshots"
        if not snapshots_dir.is_dir():
            return None
        snapshots = [p for p in snapshots_dir.iterdir() if p.is_dir()]
        if not snapshots:
            return None
        # Prefer a snapshot with the sentence-transformers structure
        # (modules.json), then any with config.json, otherwise the first one.
        with_modules = [p for p in snapshots if (p / "modules.json").exists()]
        if with_modules:
            return with_modules[0]
        with_config = [p for p in snapshots if (p / "config.json").exists()]
        if with_config:
            return with_config[0]
        return snapshots[0]

    def _resolve_model_target(self):
        """Resolve ``(model_name_or_path, cache_folder)`` for SentenceTransformer."""
        if not self.model_path:
            return self.config.model_name, self._default_cache_dir()

        path = Path(self.model_path)
        # Direct path to a model directory
        if (path / "modules.json").exists() or (path / "config.json").exists():
            return str(path), None
        # A ``models--*`` cache directory: load a usable snapshot directly
        snapshot = self._pick_snapshot(path)
        if snapshot is not None:
            return str(snapshot), None
        # Otherwise treat model_path as a hub cache root (contains models--*)
        return self.config.model_name, str(path)

    def _get_model(self):
        """Lazily load and cache the sentence-transformers model.

        Safe to call from several threads: the double-checked lock keeps the
        multi-second load from happening more than once.
        """
        if self._model is not None:
            return self._model

        with self._load_lock:
            if self._model is not None:
                return self._model
            return self._load_model()

    def _load_model(self):
        try:
            from sentence_transformers import SentenceTransformer
            import torch
        except ImportError as e:
            raise ModelAPIError(
                "Local embedding requires 'sentence-transformers' and 'torch'. "
                "Install them with: pip install 'beaver[local]'"
            ) from e

        model_name, cache_folder = self._resolve_model_target()
        device = self.device
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device

        # Force offline loading so a missing cache fails fast instead of
        # attempting a network download.
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        try:
            self._model = SentenceTransformer(
                model_name,
                cache_folder=cache_folder,
                device=device,
                local_files_only=True,
            )
        except Exception as e:
            raise ModelAPIError(
                f"Failed to load local embedding model '{model_name}' "
                f"(model_path={self.model_path!r}). Make sure the model exists "
                f"in the local HuggingFace cache: {e}"
            ) from e
        return self._model

    async def generate_embedding(self, text: str) -> np.ndarray:
        """Generate an embedding vector for the given text.

        Both loading the model (tens of seconds for a multi-GB checkpoint) and
        encoding are CPU-bound, so they run on a worker thread — running them
        inline would freeze the event loop and stall every other session.
        """
        if not getattr(self, "_is_initialized", False):
            await self.initialize()
        try:
            model = await asyncio.to_thread(self._get_model)
            vec = await asyncio.to_thread(model.encode, [text], normalize_embeddings=True)
            return np.asarray(vec[0], dtype=np.float32)
        except ModelAPIError:
            raise
        except Exception as e:
            raise ModelAPIError(f"Embedding generation failed: {e}")

    async def warm_up(self) -> None:
        """Load the model ahead of the first request (see BeaverCoreClient.warm_up)."""
        await self.generate_embedding("warm up")

    def get_embedding_model(self) -> str:
        """Get embedding model name"""
        return self.config.model_name

    def get_embedding_dim(self) -> int:
        """Get embedding vector dimension.

        Returns the real model dimension once loaded; before that falls back to
        the configured dimension (which matches for BAAI/bge-m3 = 1024).
        """
        if self._model is not None:
            return int(self._model.get_sentence_embedding_dimension())
        return self.config.dimensions

    async def count_tokens(self, text: str) -> int:
        """Count tokens in the text (simple implementation)"""
        # Simple implementation, actual token count should follow model's rules
        return len(text) // 2

    def get_model_info(self) -> Dict[str, Any]:
        """Get model information"""
        return {
            "provider": "local",
            "model_name": self.config.model_name,
            "model_path": self.model_path,
            "dimensions": self.get_embedding_dim(),
            "device": self.device,
            "initialized": self._is_initialized,
            "model_loaded": self._model is not None,
        }
