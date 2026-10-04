"""Beaver Core"""

from .services import ChatService, ConversationService, ContextManager, QuestionService, PreferenceService, ReminderService, UserService, NoteService, DocumentService
from .models import (
    MessageRole,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ConversationContext,
)

__version__ = "0.1.0"

__all__ = [
    # Service classes
    "ChatService",
    "ConversationService",
    "ContextManager",
    "QuestionService",
    "PreferenceService",
    "ReminderService",
    "UserService",
    "NoteService",
    "DocumentService",
    # Data models
    "MessageRole",
    "ChatMessage",
    "ChatRequest",
    "ChatResponse",
    "ConversationContext",
]