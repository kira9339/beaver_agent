"""Beaver Models - Model Adapter"""

from .base import (
    ModelProvider,
    ModelMessage,
    ModelResponse,
    ModelConfig,
    ModelRole,
    StreamChunk,
    ModelError,
    ModelInitializationError,
    ModelAPIError,
    ModelRateLimitError,
    ModelTokenLimitError,
    ModelConfigError,
)

from .providers import MockProvider, EmbeddingProvider, EmbeddingConfig
from .utils import TokenCounter, RateLimiter, ModelLogger

try:
    from .providers import OpenAIProvider
except ImportError:
    OpenAIProvider = None

try:
    from .providers import LocalEmbeddingProvider
except ImportError:
    LocalEmbeddingProvider = None


__all__ = [
    # base classes
    "ModelProvider",
    "ModelMessage",
    "ModelResponse",
    "ModelConfig",
    "ModelRole",
    "StreamChunk",
    # exception classes
    "ModelError",
    "ModelInitializationError",
    "ModelAPIError",
    "ModelRateLimitError",
    "ModelTokenLimitError",
    "ModelConfigError",
    # providers
    "MockProvider",
    "EmbeddingProvider",
    "EmbeddingConfig",
    # utils
    "TokenCounter",
    "RateLimiter",
    "ModelLogger",
]

if OpenAIProvider:
    __all__.append("OpenAIProvider")

if LocalEmbeddingProvider:
    __all__.append("LocalEmbeddingProvider")