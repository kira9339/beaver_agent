"""User Repository"""

from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from .base import BaseRepository
from ..models.user import User


class UserRepository(BaseRepository[User]):
    """User Repository"""
    
    def __init__(self, db: Session | AsyncSession):
        super().__init__(User, db)
    
    async def get_by_username(self, username: str) -> Optional[User]:
        """Get user by username"""
        if isinstance(self.db, AsyncSession):
            result = await self.db.execute(select(User).where(User.username == username))
            return result.scalar_one_or_none()
        else:
            return self.db.query(User).filter(User.username == username).first()
    
    async def get_by_email(self, email: str) -> Optional[User]:
        """Get user by email"""
        if isinstance(self.db, AsyncSession):
            result = await self.db.execute(select(User).where(User.email == email))
            return result.scalar_one_or_none()
        else:
            return self.db.query(User).filter(User.email == email).first()