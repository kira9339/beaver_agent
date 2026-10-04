"""Base Beaver client: response dataclasses shared by the client facade."""

from abc import ABC, abstractmethod
from typing import Optional, AsyncGenerator, List, Dict, Any
from dataclasses import dataclass


@dataclass
class ClientResponse:
    """Client response dataclass"""
    success: bool
    content: str
    metadata: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@dataclass
class ConversationInfo:
    """Conversation info"""
    id: str
    title: str
    message_count: int
    created_at: str
    updated_at: str
    summary: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class ReminderInfo:
    """Reminder info"""
    id: str
    title: str
    body: str
    due_at: Optional[str]
    status: str
    repeat_rule: Optional[str] = None
    created_at: Optional[str] = None

@dataclass
class NoteInfo:
    """Note info"""
    id: str
    title: str
    content: str
    tags: List[str]
    created_at: str
    updated_at: str

@dataclass
class PreferenceInfo:
    """Preference info"""
    id: str
    username: str
    text: str
    source_meta: Dict[str, Any]
    confidential: bool
    created_at: str

@dataclass
class UserInfo:
    """User info"""
    id: str
    username: str
    display_name: str
    email: str
    timezone: str
    created_at: str
    updated_at: str

@dataclass
class DocumentInfo:
    """Document info"""
    id: str
    file_name: str
    chunks: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    created_at: str

@dataclass
class DocumentChunkInfo:
    """Document chunk info"""
    doc_id: str
    chunk_id: str
    file_name: str
    text: str
    page_idx: int
    metadata: Dict[str, Any]
    created_at: str
    score: float = float('-inf')

class BaseBeaverClient(ABC):
    """Base Beaver client (reserved)"""
    pass
