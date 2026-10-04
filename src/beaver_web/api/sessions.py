"""Session REST API."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..deps import get_client, get_manager

router = APIRouter()


class SessionCreate(BaseModel):
    username: str
    title: Optional[str] = None


class SessionUpdate(BaseModel):
    username: str
    title: Optional[str] = None
    summary: Optional[str] = None


def _conv_dict(conv) -> dict:
    return {
        "id": conv.id,
        "title": conv.title or "new chat",
        "message_count": conv.message_count,
        "created_at": conv.created_at,
        "updated_at": conv.updated_at,
        "summary": conv.summary or "",
        "metadata": conv.metadata or {},
    }


@router.get("/sessions")
async def list_sessions(username: str, limit: int = 20, offset: int = 0):
    client = get_client()
    convs = await client.get_conversations(username, limit=limit, offset=offset)
    return {"items": [_conv_dict(c) for c in convs], "total": len(convs)}


@router.post("/sessions", status_code=201)
async def create_session(body: SessionCreate):
    client = get_client()
    conv = await client.create_conversation(
        body.username, title=body.title, metadata={"mode": "agent"}
    )
    return _conv_dict(conv)


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, username: str):
    client = get_client()
    conv = await client.get_conversation(session_id, username)
    if conv is None:
        raise HTTPException(status_code=404, detail="session not found")
    return _conv_dict(conv)


@router.patch("/sessions/{session_id}")
async def update_session(session_id: str, body: SessionUpdate):
    client = get_client()
    ok = await client.update_conversation(
        body.username, session_id, title=body.title, summary=body.summary
    )
    if not ok:
        raise HTTPException(status_code=404, detail="session not found")
    return {"ok": True}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, username: str):
    client = get_client()
    manager = get_manager()
    # Check first: deleting an unknown session used to raise ValidationError deep
    # in the service and surface as a 500, which the browser could not tell apart
    # from success.
    conv = await client.get_conversation(session_id, username)
    if conv is None:
        raise HTTPException(status_code=404, detail="session not found")
    await client.delete_conversation(session_id, username)
    await manager.remove(session_id)
    return {"ok": True}


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, username: str):
    client = get_client()
    messages = await client.get_conversation_messages(session_id, username)
    return {
        "items": [
            {"role": m.role.value if hasattr(m.role, "value") else str(m.role),
             "content": m.content,
             "metadata": m.metadata or {}}
            for m in messages
        ]
    }
