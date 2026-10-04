"""Chat related data models"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum


class MessageRole(str, Enum):
    """Message role enum"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


@dataclass
class ChatMessage:
    """Chat message"""
    role: MessageRole
    content: str
    id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None


@dataclass
class ChatRequest:
    """Chat request"""
    message: str
    username: str
    conversation_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class ChatResponse:
    """Chat response"""
    message: str
    conversation_id: str
    message_id: str
    usage: Optional[Dict[str, int]] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class ConversationContext:
    """Conversation context"""
    conversation_id: str
    messages: List[ChatMessage]
    summary: Optional[str] = None
    total_tokens: int = 0
    active_message_count: int = 0