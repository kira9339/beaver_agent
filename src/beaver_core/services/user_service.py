"""User management service"""

import uuid
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from beaver_storage.models.user import User
from beaver_storage.repositories.user import UserRepository
from beaver_core.utils import ValidationError, ServiceError

logger = logging.getLogger(__name__)


class UserService:
    """User management service"""
    
    def __init__(self, db: Session | AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)
    
    async def create_user(
        self,
        username: str,
        display_name: Optional[str] = None,
        email: Optional[str] = None,
        timezone: str = "local"
    ) -> User:
        """Create new user"""
        existing_user = await self.user_repo.get_by_username(username)
        if existing_user:
            raise ValidationError(f"Username '{username}' already exists")
        
        if email:
            existing_email = await self.user_repo.get_by_email(email)
            if existing_email:
                raise ValidationError(f"Email '{email}' is already in use")
        
        user_data = {
            "id": str(uuid.uuid4()),
            "username": username,
            "display_name": display_name or username,
            "email": email,
            "timezone": timezone
        }
        
        user = await self.user_repo.create(user_data)
        logger.info(f"Created user: {user.username} (ID: {user.id})")
        return user
    
    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get user by ID"""
        return await self.user_repo.get(user_id)
    
    async def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username"""
        return await self.user_repo.get_by_username(username)
    
    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email"""
        return await self.user_repo.get_by_email(email)
    
    async def list_users(self, limit: int = 50, offset: int = 0) -> List[User]:
        """Get user list"""
        return await self.user_repo.get_multi(skip=offset, limit=limit)
    
    async def update_user(
        self,
        username: str,
        display_name: Optional[str] = None,
        email: Optional[str] = None,
        timezone: Optional[str] = None
    ) -> Optional[User]:
        """Update user info"""
        user = await self.user_repo.get_by_username(username)
        if not user:
            return None
        
        update_data = {}
        if display_name is not None:
            update_data["display_name"] = display_name
        if email is not None:
            existing_email = await self.user_repo.get_by_email(email)
            if existing_email and existing_email.id != user.id:
                raise ValidationError(f"Email '{email}' is already in use")
            update_data["email"] = email
        if timezone is not None:
            update_data["timezone"] = timezone
        
        if update_data:
            update_data["updated_at"] = datetime.now()
            updated_user = await self.user_repo.update(user.id, update_data)
            logger.info(f"Updated user: {user.username} (ID: {user.id})")
            return updated_user
        
        return user
    
    async def delete_user(self, username: str) -> bool:
        """Delete user (soft or hard)"""
        user = await self.user_repo.get_by_username(username)
        if not user:
            raise ValidationError("User not found", field="username")
        success = await self.user_repo.delete(user.id)
        if success:
            logger.info(f"Deleted user: {user.username} (ID: {user.id})")
        return success
    
    async def user_exists(self, username: str) -> bool:
        """Check whether user exists"""
        user = await self.get_user_by_username(username)
        return user is not None