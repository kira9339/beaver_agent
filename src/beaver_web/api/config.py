"""Configuration REST API.

Backs the settings page. The API key is **never** returned in plaintext: the
response only carries ``api_key_set`` and a masked form. Because the config is
a single server-wide file (``~/.beaver/config.yaml``), every browser shares it.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import deps

router = APIRouter()

MODEL_PROVIDERS = {"mock_provider", "openai"}
EMBEDDING_PROVIDERS = {"mock_embedding_provider", "openai", "local"}


class ProviderPatch(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None


class EmbeddingPatch(ProviderPatch):
    model_path: Optional[str] = None


class UserPatch(BaseModel):
    username: Optional[str] = None


class ConfigUpdate(BaseModel):
    model_provider: Optional[ProviderPatch] = None
    embedding: Optional[EmbeddingPatch] = None
    user: Optional[UserPatch] = None


def _mask(key: Optional[str]) -> Optional[str]:
    if not key:
        return None
    if len(key) > 10:
        return f"{key[:4]}••••{key[-4:]}"
    return "••••"


def _provider_view(cfg: Any, extra: bool = False) -> Dict[str, Any]:
    view = {
        "provider": cfg.provider,
        "model": cfg.model,
        "base_url": cfg.base_url,
        "api_key_set": bool(cfg.api_key),
        "api_key_masked": _mask(cfg.api_key),
    }
    if extra:
        view["model_path"] = getattr(cfg, "model_path", None)
    return view


def _snapshot(config) -> Dict[str, Any]:
    return {
        "user": {"username": config.get_current_username()},
        "model_provider": _provider_view(config.model_provider),
        "embedding": _provider_view(config.embedding, extra=True),
    }


def _apply_api_key(target, value: Optional[str]) -> None:
    """None = leave unchanged, "" = clear, anything else = set."""
    if value is None:
        return
    target.api_key = value or None


def _apply_str(target, field: str, value: Optional[str]) -> None:
    if value is not None:
        setattr(target, field, value or None)


@router.get("/config")
async def get_config() -> Dict[str, Any]:
    return _snapshot(deps.get_client().config)


@router.put("/config")
async def update_config(body: ConfigUpdate) -> Dict[str, Any]:
    config = deps.get_client().config

    if body.model_provider is not None:
        patch = body.model_provider
        if patch.provider is not None:
            if patch.provider not in MODEL_PROVIDERS:
                raise HTTPException(400, f"unknown model provider: {patch.provider}")
            config.model_provider.provider = patch.provider
        _apply_str(config.model_provider, "model", patch.model)
        _apply_str(config.model_provider, "base_url", patch.base_url)
        _apply_api_key(config.model_provider, patch.api_key)

    if body.embedding is not None:
        patch = body.embedding
        if patch.provider is not None:
            if patch.provider not in EMBEDDING_PROVIDERS:
                raise HTTPException(400, f"unknown embedding provider: {patch.provider}")
            config.embedding.provider = patch.provider
        _apply_str(config.embedding, "model", patch.model)
        _apply_str(config.embedding, "base_url", patch.base_url)
        _apply_str(config.embedding, "model_path", patch.model_path)
        _apply_api_key(config.embedding, patch.api_key)

    if body.user is not None and body.user.username:
        config.user.username = body.user.username.strip()

    if config.model_provider.provider != "mock_provider" and not config.model_provider.api_key:
        raise HTTPException(400, f"provider '{config.model_provider.provider}' requires an api_key")
    if config.embedding.provider == "openai" and not config.embedding.api_key:
        raise HTTPException(400, "embedding provider 'openai' requires an api_key")

    config.save_config()

    try:
        deps.reload_client()
    except Exception as e:  # noqa: BLE001 - surface a readable error to the UI
        raise HTTPException(400, f"配置已保存，但重建模型连接失败: {e}")

    return _snapshot(deps.get_client().config)
