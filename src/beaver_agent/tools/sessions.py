"""Conversation (session) tools."""

from __future__ import annotations

from . import render
from .registry import tool

_SESSION_ID = {
    "type": "string",
    "description": "The session ID, obtained from session_list. Omit to refer to the current session.",
}


@tool(
    "session_list",
    "List the user's chat sessions, most recently updated first.",
    {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "default": 10},
            "offset": {"type": "integer", "default": 0},
        },
        "required": [],
    },
)
async def session_list(ctx, args) -> str:
    conversations = await ctx.client.get_conversations(
        username=ctx.username,
        limit=int(args.get("limit") or 10),
        offset=int(args.get("offset") or 0),
    )
    return render.conversations_list(conversations, ctx.username)


@tool(
    "session_show",
    "Show a session's metadata, or its recent messages when 'messages' is true.",
    {
        "type": "object",
        "properties": {
            "session_id": _SESSION_ID,
            "messages": {"type": "boolean", "description": "When true, also return the recent messages.", "default": False},
            "limit": {"type": "integer", "description": "How many recent messages to return.", "default": 20},
        },
        "required": [],
    },
)
async def session_show(ctx, args) -> str:
    session_id = args.get("session_id") or ctx.session_id
    conversation = await ctx.client.get_conversation(session_id, ctx.username)
    if not conversation:
        return f"session {session_id} not exist or no permission"
    if not args.get("messages"):
        return render.session_detail(conversation)
    messages = await ctx.client.get_conversation_messages(session_id, ctx.username)
    return render.session_detail(conversation) + "\n\n" + render.session_messages(
        messages, limit=int(args.get("limit") or 20)
    )


@tool(
    "session_delete",
    "Delete a chat session and all of its messages. Requires user confirmation.",
    {"type": "object", "properties": {"session_id": _SESSION_ID}, "required": ["session_id"]},
    requires_confirm=True,
    confirm_title="删除会话",
    confirm_render=lambda a: (
        f"session ID: {a.get('session_id')}\n"
        "This session and all of its messages will be permanently deleted."
    ),
)
async def session_delete(ctx, args) -> str:
    session_id = args["session_id"]
    conversation = await ctx.client.get_conversation(session_id, ctx.username)
    if not conversation:
        return f"session {session_id} not exist or no permission"
    await ctx.client.delete_conversation(session_id, ctx.username)
    return render.session_deleted(conversation.title, session_id)
