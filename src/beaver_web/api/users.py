"""User REST API.

``by-username`` is the username-only login path (get-or-create); the rest backs
the user management section of the settings page.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..deps import get_client

router = APIRouter()


class UserCreate(BaseModel):
    username: str
    display_name: Optional[str] = None
    email: Optional[str] = None
    timezone: str = "local"


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    email: Optional[str] = None
    timezone: Optional[str] = None


def _user_dict(user) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "email": user.email,
        "timezone": user.timezone,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


def _validate_timezone(timezone: Optional[str]) -> None:
    if timezone is None or timezone == "local":
        return
    if (not timezone.startswith("UTC") or len(timezone) != 6
            or timezone[3] not in "+-" or not timezone[4:].isdigit()
            or int(timezone[3:]) not in range(-12, 13)):
        raise HTTPException(400, "invalid timezone format, please use UTC+/-HH (e.g. UTC-10, UTC+08, UTC+12)")


@router.get("/users")
async def list_users(limit: int = 50, offset: int = 0):
    users = await get_client().list_users(limit=limit, offset=offset)
    return {"items": [_user_dict(u) for u in users]}


@router.post("/users", status_code=201)
async def create_user(body: UserCreate):
    client = get_client()
    username = body.username.strip()
    if not username:
        raise HTTPException(400, "username cannot be empty")
    _validate_timezone(body.timezone)
    if await client.user_exists(username):
        raise HTTPException(409, f"user '{username}' already exists")
    user = await client.create_user(
        username=username,
        display_name=body.display_name,
        email=body.email,
        timezone=body.timezone,
    )
    return _user_dict(user)


@router.get("/users/by-username/{username}")
async def get_or_create_user(username: str):
    """Return the user; create it if it does not exist yet."""
    client = get_client()
    user = await client.get_user_by_username(username)
    if user is None:
        user = await client.create_user(username=username)
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "email": user.email,
        "timezone": user.timezone,
    }


@router.patch("/users/{username}")
async def update_user(username: str, body: UserUpdate):
    client = get_client()
    _validate_timezone(body.timezone)
    user = await client.update_user(
        username=username,
        display_name=body.display_name,
        email=body.email,
        timezone=body.timezone,
    )
    if user is None:
        raise HTTPException(404, "user not found")
    return _user_dict(user)


@router.delete("/users/{username}")
async def delete_user(username: str):
    client = get_client()
    if username == client.config.get_current_username():
        raise HTTPException(400, "cannot delete the current user")
    ok = await client.delete_user(username)
    if not ok:
        raise HTTPException(404, "user not found")
    return {"ok": True}
