"""Note Repository"""

from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from .base import BaseRepository
from ..models.note import Note


class NoteRepository(BaseRepository[Note]):
    """Note Repository"""

    def __init__(self, db: Session | AsyncSession):
        super().__init__(Note, db)

    async def get_by_username(self, username: str, limit: int = 50) -> List[Note]:
        if isinstance(self.db, AsyncSession):
            result = await self.db.execute(
                select(Note)
                .where(Note.username == username)
                .order_by(Note.updated_at.desc())
                .limit(limit)
            )
            return result.scalars().all()
        else:
            return (
                self.db.query(Note)
                .filter(Note.username == username)
                .order_by(Note.updated_at.desc())
                .limit(limit)
                .all()
            )

    async def search(
        self, username: str, keyword: str, limit: int = 50
    ) -> List[Note]:
        kw = f"%{keyword}%"
        if isinstance(self.db, AsyncSession):
            result = await self.db.execute(
                select(Note)
                .where(
                    (Note.username == username)
                    & or_(Note.title.like(kw), Note.content.like(kw))
                )
                .order_by(Note.updated_at.desc())
                .limit(limit)
            )
            return result.scalars().all()
        else:
            return (
                self.db.query(Note)
                .filter(
                    (Note.username == username)
                    & or_(Note.title.like(kw), Note.content.like(kw))
                )
                .order_by(Note.updated_at.desc())
                .limit(limit)
                .all()
            )