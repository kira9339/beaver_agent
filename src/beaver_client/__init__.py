"""Beaver client layer: the application-facing facade over beaver_core services.

``beaver_client`` is the single entry point both the web layer and the agent tool
layer use. It owns the model/embedding providers and knows nothing about how
the caller presents results.
"""

from .config import (
    BeaverConfig,
    BeaverUserConfig,
    BeaverServerConfig,
    BeaverModelProviderConfig,
    BeaverEmbeddingConfig,
    BeaverFeatureConfig,
)
from .base import (
    BaseBeaverClient,
    ClientResponse,
    ConversationInfo,
    ReminderInfo,
    NoteInfo,
    PreferenceInfo,
    UserInfo,
    DocumentInfo,
    DocumentChunkInfo,
)
from .core import BeaverCoreClient, ServiceType

__all__ = [
    "BeaverConfig",
    "BeaverUserConfig",
    "BeaverServerConfig",
    "BeaverModelProviderConfig",
    "BeaverEmbeddingConfig",
    "BeaverFeatureConfig",
    "BaseBeaverClient",
    "ClientResponse",
    "ConversationInfo",
    "ReminderInfo",
    "NoteInfo",
    "PreferenceInfo",
    "UserInfo",
    "DocumentInfo",
    "DocumentChunkInfo",
    "BeaverCoreClient",
    "ServiceType",
]
