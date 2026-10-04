"""Message Repository"""

from typing import List
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from .base import BaseRepository
from ..models.message import Message


class MessageRepository(BaseRepository[Message]):
    """Message Repository"""
    
    def __init__(self, db: Session | AsyncSession):
        super().__init__(Message, db)
    
    async def get_by_conversation(self, conversation_id: str, skip: int = 0, limit: int = 100) -> List[Message]:
        """Get message list in conversation"""
        if isinstance(self.db, AsyncSession):
            result = await self.db.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at)
                .offset(skip)
                .limit(limit)
            )
            return result.scalars().all()
        else:
            return (
                self.db.query(Message)
                .filter(Message.conversation_id == conversation_id)
                .order_by(Message.created_at)
                .offset(skip)
                .limit(limit)
                .all()
            )
    
    async def get_recent_by_conversation(self, conversation_id: str, limit: int = 20) -> List[Message]:
        """Get recent message list in conversation"""
        if isinstance(self.db, AsyncSession):
            result = await self.db.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(desc(Message.created_at))
                .limit(limit)
            )
            return list(reversed(result.scalars().all()))
        else:
            messages = (
                self.db.query(Message)
                .filter(Message.conversation_id == conversation_id)
                .order_by(desc(Message.created_at))
                .limit(limit)
                .all()
            )
            return list(reversed(messages))