import asyncio
import hashlib
import numpy as np
from typing import Dict, Any, Optional

from .embedding_provider import EmbeddingConfig


class MockEmbeddingProvider:
    """Mock embedding provider for testing"""

    def __init__(
        self,
        config: EmbeddingConfig,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        delay: float = 0.0,
    ):
        self.config = config
        self.api_key = api_key
        self.base_url = base_url
        self.delay = delay
        self.call_count = 0
        self._is_initialized = False

    async def initialize(self) -> None:
        """Initialize mock embedding provider"""
        self._is_initialized = True

    async def generate_embedding(self, text: str) -> np.ndarray:
        """Generate a deterministic mock embedding vector"""
        if not getattr(self, "_is_initialized", False):
            await self.initialize()

        if self.delay and self.delay > 0:
            await asyncio.sleep(self.delay)

        self.call_count += 1

        digest = hashlib.sha256(text.encode("utf-8")).digest()
        dim = self.config.dimensions
        buf = (digest * ((dim // len(digest)) + 1))[:dim]
        vec = np.array([(b - 128) / 128.0 for b in buf], dtype=np.float32)
        return vec

    def get_embedding_model(self) -> str:
        return self.config.model_name

    def get_embedding_dim(self) -> int:
        return self.config.dimensions

    async def count_tokens(self, text: str) -> int:
        return len(text) // 2

    def get_model_info(self) -> Dict[str, Any]:
        return {
            "provider": "mock",
            "model_name": self.config.model_name,
            "dimensions": self.config.dimensions,
            "initialized": self._is_initialized,
            "call_count": self.call_count,
        }