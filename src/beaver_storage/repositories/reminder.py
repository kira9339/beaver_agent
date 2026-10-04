"""Reminder Repository"""

from datetime import datetime
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from .base import BaseRepository
from ..models.reminder import Reminder


class ReminderRepository(BaseRepository[Reminder]):
    """Reminder Repository"""
    
    def __init__(self, db: Session | AsyncSession):
        super().__init__(Reminder, db)
    
    async def get_by_user(self, user_id: str, status: Optional[str] = None, 
                         limit: int = 100) -> List[Reminder]:
        """Get reminders by user id"""
        if isinstance(self.db, AsyncSession):
            query = select(Reminder).where(Reminder.user_id == user_id)
            if status:
                query = query.where(Reminder.status == status)
            query = query.order_by(Reminder.due_at).limit(limit)
            
            result = await self.db.execute(query)
            return result.scalars().all()
        else:
            query = self.db.query(Reminder).filter(Reminder.user_id == user_id)
            if status:
                query = query.filter(Reminder.status == status)
            return query.order_by(Reminder.due_at).limit(limit).all()
    
    async def get_due_reminders(self, before: datetime) -> List[Reminder]:
        """Get pending reminders"""
        if isinstance(self.db, AsyncSession):
            result = await self.db.execute(
                select(Reminder)
                .where(and_(
                    Reminder.status == "pending",
                    Reminder.due_at <= before
                ))
                .order_by(Reminder.due_at)
            )
            return result.scalars().all()
        else:
            return (
                self.db.query(Reminder)
                .filter(and_(
                    Reminder.status == "pending",
                    Reminder.due_at <= before
                ))
                .order_by(Reminder.due_at)
                .all()
            )