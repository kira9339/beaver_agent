"""Chat service"""

import uuid
import logging
from datetime import datetime
from typing import Optional, AsyncGenerator, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from ..models.chat import (
    ChatRequest, 
    ChatResponse, 
    ChatMessage, 
    MessageRole,
    ConversationContext
)
from .context_manager import ContextManager
from beaver_models import ModelProvider, ModelMessage, StreamChunk
from beaver_storage.models.conversation import Conversation
from beaver_storage.models.message import Message
from beaver_storage.repositories.conversation import ConversationRepository
from beaver_storage.repositories.message import MessageRepository
from config.settings import Settings
from beaver_core.utils import ValidationError, ServiceError

logger = logging.getLogger(__name__)


class ChatService:
    """Chat service"""
    
    def __init__(
        self,
        db: Session | AsyncSession,
        model_provider: ModelProvider,
        settings: Settings
    ):
        self.db = db
        self.model_provider = model_provider
        self.settings = settings
        self.context_manager = ContextManager(settings)
        
        # Initialize repositories
        self.conversation_repo = ConversationRepository(db)
        self.message_repo = MessageRepository(db)
    
    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Handle chat request"""
        if not request.username or not str(request.username).strip():
            raise ValidationError("username cannot be empty", field="username")
        if not request.message or not str(request.message).strip():
            raise ValidationError("message cannot be empty", field="message")
        conversation = await self._get_or_create_conversation(
            request.conversation_id,
            request.username
        )
        await self._save_user_message(
            conversation.id,
            request.message,
            request.metadata
        )
        context = await self._build_conversation_context(conversation.id)
        ai_response = await self._generate_ai_response(context)
        ai_message = await self._save_ai_message(
            conversation.id,
            ai_response.content,
            ai_response.usage
        )
        await self._update_conversation(conversation, context)
        await self._check_and_generate_summary(conversation)
        return ChatResponse(
            message=ai_response.content,
            conversation_id=conversation.id,
            message_id=ai_message.id,
            usage=ai_response.usage,
            metadata=ai_response.metadata
        )
    
    async def stream_chat(
        self,
        messages: List[ModelMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs # e.g., tool_choice="auto"
    ) -> AsyncGenerator[StreamChunk, None]:
        """Streaming chat"""
        async for chunk in self.model_provider.stream_generate(
            messages,
            tools=tools,
            **kwargs
        ):
            yield chunk
    
    async def get_conversation_history(
        self, 
        conversation_id: str, 
        limit: int = 50
    ) -> List[ChatMessage]:
        """Get conversation history"""
        messages = await self.message_repo.get_by_conversation(
            conversation_id, 
            limit=limit
        )
        
        return [
            ChatMessage(
                role=MessageRole(msg.role),
                content=msg.content,
                metadata=msg.meta,
                created_at=msg.created_at
            )
            for msg in messages
        ]
    
    async def _get_or_create_conversation(
        self, 
        conversation_id: Optional[str], 
        username: str
    ) -> Conversation:
        """Get or create conversation"""
        if conversation_id:
            conversation = await self.conversation_repo.get(conversation_id)
            if conversation:
                if conversation.username != username:
                    raise ValidationError("permission denied for conversation", field="conversation_id")
                return conversation
        
        # 创建新会话 - 修复：传递字典而非对象
        conversation_data = {
            "id": str(uuid.uuid4()),
            "username": username,
            "title": "new chat",
            "conversation_metadata": {}
        }
        
        return await self.conversation_repo.create(conversation_data)
    
    async def _save_user_message(
        self, 
        conversation_id: str, 
        content: str, 
        metadata: Optional[Dict[str, Any]] = None
    ) -> Message:
        """Save user message"""
        message_data = {
            "id": str(uuid.uuid4()),
            "conversation_id": conversation_id,
            "role": MessageRole.USER.value,
            "content": content,
            "meta": metadata or {}
        }
        
        return await self.message_repo.create(message_data)
    
    async def _save_ai_message(
        self, 
        conversation_id: str, 
        content: str, 
        usage: Optional[Dict[str, int]] = None
    ) -> Message:
        """Save AI message"""
        metadata = {"usage": usage} if usage else {}
        
        message_data = {
            "id": str(uuid.uuid4()),
            "conversation_id": conversation_id,
            "role": MessageRole.ASSISTANT.value,
            "content": content,
            "tokens": usage.get("total_tokens") if usage else None,
            "meta": metadata
        }
        
        return await self.message_repo.create(message_data)
    
    async def _build_conversation_context(self, conversation_id: str) -> ConversationContext:
        """Build conversation context"""
        # Get conversation info
        conversation = await self.conversation_repo.get_with_messages(conversation_id)
        
        # Convert message format
        chat_messages = [
            ChatMessage(
                role=MessageRole(msg.role),
                content=msg.content,
                metadata=msg.meta,
                created_at=msg.created_at
            )
            for msg in conversation.messages
        ]
        
        # Build context
        context = self.context_manager.build_context(
            chat_messages, 
            conversation.summary
        )
        context.conversation_id = conversation_id
        
        return context
    
    async def _generate_ai_response(self, context: ConversationContext):
        """Generate AI response"""
        model_messages = self.context_manager.convert_to_model_messages(context.messages)
        return await self.model_provider.generate(model_messages)
    
    async def _update_conversation(
        self, 
        conversation: Conversation, 
        context: ConversationContext
    ):
        """Update conversation info"""
        conversation.updated_at = datetime.now()
        
        # Update title (if still default)
        if conversation.title == "new chat" and context.messages:
            first_user_message = next(
                (msg for msg in context.messages if msg.role == MessageRole.USER), 
                None
            )
            if first_user_message:
                conversation.title = first_user_message.content[:20] + "..."
        
        update_data = {
            "updated_at": conversation.updated_at,
            "title": conversation.title
        }
        await self.conversation_repo.update(conversation.id, update_data)
    
    async def _check_and_generate_summary(self, conversation: Conversation):
        """Check and generate summary"""
        message_count = len(conversation.messages)
        
        if (self.context_manager.should_generate_summary(message_count) and 
            not conversation.summary):
            
            # Get all messages
            chat_messages = [
                ChatMessage(
                    role=MessageRole(msg.role),
                    content=msg.content,
                    created_at=msg.created_at
                )
                for msg in conversation.messages
            ]
            
            # Generate summary
            summary = await self.context_manager.generate_summary(
                chat_messages, 
                self.model_provider
            )
            
            update_data = {"summary": summary}
            await self.conversation_repo.update(conversation.id, update_data)