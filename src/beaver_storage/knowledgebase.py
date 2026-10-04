"""Knowledge base connection configuration module"""

from typing import Optional

from chromadb import PersistentClient
from config.settings import settings

_client: Optional[PersistentClient] = None


def init_knowledge_base() -> PersistentClient:
    """Initialize knowledge base Chroma persistent client"""
    global _client
    try:
        _client = PersistentClient(path=settings.knowledge_base.persist_dir)
    except Exception as e:
        # In production, should log this error properly
        raise ConnectionError(f"Failed to initialize Chroma vector database: {str(e)}")
    return _client


def get_knowledge_base_connection() -> PersistentClient:
    """Get knowledge base connection"""
    # Check if client exists, initialize if not
    global _client
    if _client is None:
        _client = init_knowledge_base()
    # The Chroma client is a process-global persistent client; return it directly
    # for the Repository to create / access collections.
    return _client
