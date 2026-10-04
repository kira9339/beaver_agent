"""Question Value Repository"""

from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import Session

from .base import BaseRepository
from ..models.question_value import QuestionValue


class QuestionValueRepository(BaseRepository[QuestionValue]):
    """Question Value Repository"""
    
    def __init__(self, db: Session | AsyncSession):
        super().__init__(QuestionValue, db)
    
    async def get_by_username(self, username: str) -> Optional[QuestionValue]:
        """Get question value by username"""
        if isinstance(self.db, AsyncSession):
            result = await self.db.execute(
                select(QuestionValue).where(QuestionValue.username == username)
            )
            return result.scalar_one_or_none()
        else:
            return self.db.query(QuestionValue).filter(QuestionValue.username == username).first()
