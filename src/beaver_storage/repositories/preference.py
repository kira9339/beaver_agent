"""Preference Record Repository"""

from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import Session

from .base import BaseRepository
from ..models.preference import PreferenceRecord


class PreferenceRecordRepository(BaseRepository[PreferenceRecord]):
    """Preference Record Repository"""
    
    def __init__(self, db: Session | AsyncSession):
        super().__init__(PreferenceRecord, db)
    
    async def get_by_user(self, username: str, limit: int = 100) -> List[PreferenceRecord]:
        """Get preference records by username"""
        if isinstance(self.db, AsyncSession):
            result = await self.db.execute(
                select(PreferenceRecord)
                .where(PreferenceRecord.username == username)
                .order_by(PreferenceRecord.created_at.desc())
                .limit(limit)
            )
            return result.scalars().all()
        else:
            return (
                self.db.query(PreferenceRecord)
                .filter(PreferenceRecord.username == username)
                .order_by(PreferenceRecord.created_at.desc())
                .limit(limit)
                .all()
            )
    
    async def count_by_user(self, username: str) -> int:
        """Count preference records by username"""
        if isinstance(self.db, AsyncSession):
            result = await self.db.execute(
                select(func.count(PreferenceRecord.id))
                .where(PreferenceRecord.username == username)
            )
            return result.scalar() or 0
        else:
            return (
                self.db.query(PreferenceRecord)
                .filter(PreferenceRecord.username == username)
                .count()
            )
    
    async def delete_multiple(self, record_ids: List[str]) -> bool:
        """Delete multiple preference records by record ids"""
        try:
            if isinstance(self.db, AsyncSession):
                for record_id in record_ids:
                    await self.delete(record_id)
                return True
            else:
                self.db.query(PreferenceRecord).filter(
                    PreferenceRecord.id.in_(record_ids)
                ).delete(synchronize_session=False)
                return True
        except Exception:
            return False