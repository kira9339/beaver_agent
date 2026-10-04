"""Context management service"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from ..models.chat import ChatMessage, ConversationContext, MessageRole
from beaver_models import ModelProvider, ModelMessage, ModelRole as ModelMessageRole
from config.settings import Settings

logger = logging.getLogger(__name__)


class ContextManager:
    """Conversation context manager"""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.max_active_messages = settings.context.max_active_messages
        self.max_context_tokens = settings.context.max_context_tokens
        self.summary_threshold = settings.context.summary_threshold
    
    def build_context(
        self, 
        messages: List[ChatMessage], 
        summary: Optional[str] = None
    ) -> ConversationContext:
        """Build conversation context"""
        # Sort messages by time
        sorted_messages = sorted(messages, key=lambda m: m.created_at or datetime.min)
        
        # Estimate total tokens (simple heuristic)
        total_tokens = sum(len(msg.content.split()) * 1.3 for msg in sorted_messages)
        
        # Apply sliding window strategy
        active_messages = self._apply_sliding_window(sorted_messages, summary)
        
        return ConversationContext(
            conversation_id="",  # Will be set at service layer
            messages=active_messages,
            summary=summary,
            total_tokens=int(total_tokens),
            active_message_count=len(active_messages)
        )
    
    def _apply_sliding_window(
        self, 
        messages: List[ChatMessage], 
        summary: Optional[str] = None
    ) -> List[ChatMessage]:
        """Apply sliding window strategy"""
        if len(messages) <= self.max_active_messages:
            return messages
        
        # Keep the most recent messages
        recent_messages = messages[-self.max_active_messages:]
        
        # If summary exists, add it as a system message at the beginning
        if summary:
            summary_message = ChatMessage(
                role=MessageRole.SYSTEM,
                content=f"summary: {summary}",
                metadata={"type": "summary"}
            )
            return [summary_message] + recent_messages
        
        return recent_messages
    
    def convert_to_model_messages(self, messages: List[ChatMessage]) -> List[ModelMessage]:
        """Convert to model message format"""
        model_messages = []
        
        for msg in messages:
            # Convert role
            if msg.role == MessageRole.USER:
                model_role = ModelMessageRole.USER
            elif msg.role == MessageRole.ASSISTANT:
                model_role = ModelMessageRole.ASSISTANT
            else:
                model_role = ModelMessageRole.SYSTEM
            
            model_messages.append(ModelMessage(
                role=model_role,
                content=msg.content,
                metadata=msg.metadata
            ))
        
        return model_messages
    
    def should_generate_summary(self, message_count: int) -> bool:
        """Determine whether to generate a summary"""
        return message_count >= self.summary_threshold
    
    async def generate_summary(
        self, 
        messages: List[ChatMessage], 
        model_provider: ModelProvider
    ) -> str:
        """Generate conversation summary"""
        if not messages:
            return ""
        
        # Build summary prompt
        conversation_text = "\n".join([
            f"{msg.role.value}: {msg.content}" 
            for msg in messages
        ])
        
        summary_prompt = f"""
Please generate a summary of the following conversation, highlighting key information and decisions.
The summary should be concise and not exceed 200 words.

{conversation_text}

Summary: """
        
        summary_messages = [ModelMessage(
            role=ModelMessageRole.USER,
            content=summary_prompt
        )]
        
        response = await model_provider.generate(summary_messages)
        return response.content.strip()