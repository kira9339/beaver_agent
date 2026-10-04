"""Conversation Repository"""

from typing import List
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, selectinload
from .base import BaseRepository
from ..models.conversation import Conversation


class ConversationRepository(BaseRepository[Conversation]):
    """Conversation Repository"""
    
    def __init__(self, db: Session | AsyncSession):
        super().__init__(Conversation, db)
    
    async def get_by_username(self, username: str, skip: int = 0, limit: int = 100) -> List[Conversation]:
        """Get user conversation list"""
        if isinstance(self.db, AsyncSession):
            result = await self.db.execute(
                select(Conversation)
                .options(selectinload(Conversation.messages))  # 预加载messages
                .where(Conversation.username == username)
                .order_by(desc(Conversation.updated_at))
                .offset(skip)
                .limit(limit)
            )
            return result.scalars().all()
        else:
            return (
                self.db.query(Conversation)
                .options(selectinload(Conversation.messages))  # 预加载messages
                .filter(Conversation.username == username)
                .order_by(desc(Conversation.updated_at))
                .offset(skip)
                .limit(limit)
                .all()
            )
    
    async def get_with_messages(self, conversation_id: str) -> Conversation:
        """Get conversation with messages"""
        if isinstance(self.db, AsyncSession):
            result = await self.db.execute(
                select(Conversation)
                .options(selectinload(Conversation.messages))
                .where(Conversation.id == conversation_id)
            )
            return result.scalar_one_or_none()
        else:
            return (
                self.db.query(Conversation)
                .options(selectinload(Conversation.messages))
                .filter(Conversation.id == conversation_id)
                .first()
            )