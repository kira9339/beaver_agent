"""Note service"""

import uuid
import logging
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from beaver_storage.models.note import Note
from beaver_storage.repositories.note import NoteRepository
from beaver_core.utils import ValidationError, ServiceError

logger = logging.getLogger(__name__)


class NoteService:
    """Note service"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = NoteRepository(db)

    async def create_note(
        self, username: str, title: str, content: str, tags: Optional[List[str]] = None
    ) -> Note:
        if not title or not str(title).strip():
            raise ValidationError("Title cannot be empty", field="title")
        if not content or not str(content).strip():
            raise ValidationError("Content cannot be empty", field="content")
        note_data = {
                "id": str(uuid.uuid4()),
                "username": username,
                "title": title.strip(),
                "content": content.strip(),
                "tags": tags,
            }
        note = await self.repo.create(note_data)
        logger.info(f"Created note {note.id} for user {username}")
        return note

    async def get_user_notes(self, username: str, limit: int = 50) -> List[Note]:
        return await self.repo.get_by_username(username, limit=limit)

    async def get_note_by_id(self, username: str, note_id: str) -> Optional[Note]:
        note = await self.repo.get(note_id)
        if not note or note.username != username:
            return None
        return note

    async def update_note(
        self,
        username: str,
        note_id: str,
        title: Optional[str] = None,
        content: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Optional[Note]:
        note = await self.repo.get(note_id)
        if not note or note.username != username:
            return None
        update_data = {}
        if title is not None:
            update_data["title"] = title.strip()
        if content is not None:
            update_data["content"] = content.strip()
        if tags is not None:
            update_data["tags"] = tags
        if update_data:
            update_data["updated_at"] = note.updated_at
            return await self.repo.update(note_id, update_data)
        return note

    async def delete_note(self, username: str, note_id: str) -> bool:
        note = await self.repo.get(note_id)
        if not note or note.username != username:
            return False
        return await self.repo.delete(note_id)

    async def search_notes(
        self, username: str, keyword: str, tag: Optional[str] = None, limit: int = 50
    ) -> List[Note]:
        notes = await self.repo.search(username=username, keyword=keyword, limit=limit)
        if tag:
            notes = [n for n in notes if (n.tags or []) and tag in n.tags]
        return notes