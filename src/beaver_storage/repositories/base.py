"""Base Repository"""

from typing import TypeVar, Generic, Type, Optional, List, Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from sqlalchemy.orm import Session
from ..database import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Base Repository"""
    
    def __init__(self, model: Type[ModelType], db: Session | AsyncSession):
        self.model = model
        self.db = db
    
    async def create(self, obj_in: Dict[str, Any]) -> ModelType:
        """Create object"""
        db_obj = self.model(**obj_in)
        self.db.add(db_obj)
        if isinstance(self.db, AsyncSession):
            await self.db.commit()
            await self.db.refresh(db_obj)
        else:
            self.db.commit()
            self.db.refresh(db_obj)
        return db_obj
    
    async def get(self, id: Any) -> Optional[ModelType]:
        """Get object by ID"""
        if isinstance(self.db, AsyncSession):
            result = await self.db.execute(select(self.model).where(self.model.id == id))
            return result.scalar_one_or_none()
        else:
            return self.db.query(self.model).filter(self.model.id == id).first()
    
    async def get_multi(self, skip: int = 0, limit: int = 100) -> List[ModelType]:
        """Get multiple objects"""
        if isinstance(self.db, AsyncSession):
            result = await self.db.execute(select(self.model).offset(skip).limit(limit))
            return result.scalars().all()
        else:
            return self.db.query(self.model).offset(skip).limit(limit).all()
    
    async def update(self, id: Any, obj_in: Dict[str, Any]) -> Optional[ModelType]:
        """Update object"""
        if isinstance(self.db, AsyncSession):
            await self.db.execute(
                update(self.model).where(self.model.id == id).values(**obj_in)
            )
            await self.db.commit()
            return await self.get(id)
        else:
            db_obj = self.db.query(self.model).filter(self.model.id == id).first()
            if db_obj:
                for field, value in obj_in.items():
                    setattr(db_obj, field, value)
                self.db.commit()
                self.db.refresh(db_obj)
            return db_obj
    
    async def delete(self, id: Any) -> bool:
        """Delete object"""
        if isinstance(self.db, AsyncSession):
            result = await self.db.execute(delete(self.model).where(self.model.id == id))
            await self.db.commit()
            return result.rowcount > 0
        else:
            db_obj = self.db.query(self.model).filter(self.model.id == id).first()
            if db_obj:
                self.db.delete(db_obj)
                self.db.commit()
                return True
            return False