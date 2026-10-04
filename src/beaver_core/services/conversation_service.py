"""Conversation service"""

import uuid
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from ..models.chat import ChatMessage, MessageRole
from beaver_storage.models.conversation import Conversation
from beaver_storage.repositories.conversation import ConversationRepository
from beaver_storage.repositories.message import MessageRepository
from beaver_core.utils import ValidationError, ServiceError

logger = logging.getLogger(__name__)


class ConversationService:
    """Conversation service"""
    
    def __init__(self, db: Session | AsyncSession):
        self.db = db
        self.conversation_repo = ConversationRepository(db)
        self.message_repo = MessageRepository(db)
    
    async def create_conversation(
        self, 
        username: str, 
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Conversation:
        """Create new conversation"""
        conversation_data = {
            "id": str(uuid.uuid4()),
            "username": username,
            "title": title or "new chat",
            "conversation_metadata": metadata or {}
        }
        
        return await self.conversation_repo.create(conversation_data)
    
    async def get_user_conversations(
        self, 
        username: str, 
        skip: int = 0, 
        limit: int = 20
    ) -> List[Conversation]:
        """Get user conversation list"""
        return await self.conversation_repo.get_by_username(username, skip, limit)
    
    async def get_conversation(
        self, 
        conversation_id: str, 
        username: Optional[str] = None
    ) -> Optional[Conversation]:
        """Get conversation details"""
        # Use get_with_messages to preload the messages relationship
        conversation = await self.conversation_repo.get_with_messages(conversation_id)
        if conversation and username and conversation.username != username:
            raise ValidationError("No permission to access conversation", field="conversation_id")
        return conversation
    
    async def update_conversation(
        self, 
        conversation_id: str, 
        username: str,
        title: Optional[str] = None,
        summary: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Update conversation"""
        try:
            conversation = await self.get_conversation(conversation_id, username)
            if not conversation:
                raise ValidationError("Conversation not exist or no permission", field="conversation_id")
            update_data: Dict[str, Any] = {}
            if title is not None:
                update_data["title"] = title
            if summary is not None:
                update_data["summary"] = summary
            if metadata is not None:
                update_data["conversation_metadata"] = metadata
            update_data["updated_at"] = datetime.now()
            await self.conversation_repo.update(conversation_id, update_data)
            return True
        except Exception as e:
            raise ServiceError(f"Update conversation failed: {e}")
    
    async def delete_conversation(
        self, 
        conversation_id: str, 
        username: str
    ) -> bool:
        """Delete conversation"""
        conversation = await self.get_conversation(conversation_id, username)
        if not conversation:
            raise ValidationError("Conversation not exist or no permission", field="conversation_id")
        await self.conversation_repo.delete(conversation_id)
        return True
    
    async def get_conversation_messages(
        self, 
        conversation_id: str, 
        username: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[ChatMessage]:
        """Get conversation messages"""
        if username:
            conversation = await self.get_conversation(conversation_id, username)
            if not conversation:
                raise ValidationError("Conversation not exist or no permission", field="conversation_id")
        messages = await self.message_repo.get_by_conversation(
            conversation_id, skip, limit
        )
        
        return [
            ChatMessage(
                id=msg.id,
                role=MessageRole(msg.role),
                content=msg.content,
                metadata=msg.meta,
                created_at=msg.created_at
            )
            for msg in messages
        ]