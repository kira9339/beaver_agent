"""Note tools."""

from __future__ import annotations

from beaver_core.utils import ValidationError

from . import render
from .registry import tool

_NOTE_ID = {"type": "string", "description": "The note ID, obtained from note_list or note_search."}


@tool(
    "note_add",
    "Create a note for the user. Requires user confirmation.",
    {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "The note body. Required and cannot be empty."},
            "title": {"type": "string", "description": "Note title. Defaults to the first 8 characters of the content."},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional tags."},
        },
        "required": ["content"],
    },
    requires_confirm=True,
    confirm_title="创建笔记",
    confirm_render=lambda a: (
        f"title: {a.get('title') or (a.get('content') or '')[:8]}\n"
        f"tags: {', '.join(a.get('tags') or []) or 'none'}\n"
        f"content:\n{a.get('content', '')}"
    ),
)
async def note_add(ctx, args) -> str:
    content = (args.get("content") or "").strip()
    if not content:
        raise ValidationError("content cannot be empty", field="content")
    title = (args.get("title") or "").strip() or content[:8]
    tags = [t.strip() for t in (args.get("tags") or []) if t and t.strip()]
    note = await ctx.client.create_note(
        username=ctx.username, title=title, content=content, tags=tags,
    )
    return render.note_created(note)


@tool(
    "note_list",
    "List the user's notes, most recent first.",
    {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": "Maximum number of notes to return.", "default": 20},
            "detail": {"type": "boolean", "description": "When true, return the full content of each note.", "default": False},
        },
        "required": [],
    },
)
async def note_list(ctx, args) -> str:
    limit = int(args.get("limit") or 20)
    detail = bool(args.get("detail"))
    notes = await ctx.client.get_notes(username=ctx.username, limit=limit)
    if not notes:
        return "no note found"
    if detail:
        blocks = []
        for i, n in enumerate(notes, 1):
            blocks.append(f"#{i}\n{render.note_detail(n)}")
        return "\n\n".join(blocks)
    return render.notes_list(notes)


@tool(
    "note_show",
    "Show the full content of a single note.",
    {"type": "object", "properties": {"note_id": _NOTE_ID}, "required": ["note_id"]},
)
async def note_show(ctx, args) -> str:
    note = await ctx.client.get_note_by_id(username=ctx.username, note_id=args["note_id"])
    if not note:
        return "note not found or no permission"
    return render.note_detail(note)


@tool(
    "note_search",
    "Search the user's notes by keyword, optionally filtered by tag.",
    {
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "description": "Keyword to search for in note titles and content."},
            "tag": {"type": "string", "description": "Optional tag to filter by."},
            "limit": {"type": "integer", "default": 20},
            "detail": {"type": "boolean", "description": "When true, return the full content of each match.", "default": False},
        },
        "required": ["keyword"],
    },
)
async def note_search(ctx, args) -> str:
    limit = int(args.get("limit") or 20)
    notes = await ctx.client.search_notes(
        username=ctx.username,
        keyword=args["keyword"],
        tag=args.get("tag"),
        limit=limit,
    )
    if not notes:
        return "no note searched"
    if args.get("detail"):
        blocks = []
        for i, n in enumerate(notes, 1):
            blocks.append(f"#{i}\n{render.note_detail(n)}")
        return "\n\n".join(blocks)
    return render.note_search_results(notes)


@tool(
    "note_update",
    "Update an existing note. Only the provided fields are changed. Requires user confirmation.",
    {
        "type": "object",
        "properties": {
            "note_id": _NOTE_ID,
            "title": {"type": "string", "description": "New title. Omit to keep the current one."},
            "content": {"type": "string", "description": "New content. Omit to keep the current one."},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "New tags, replacing the old ones. Omit to keep the current ones."},
        },
        "required": ["note_id"],
    },
    requires_confirm=True,
    confirm_title="更新笔记",
    confirm_render=lambda a: (
        f"note ID: {a.get('note_id')}\n"
        f"new title: {a.get('title') or '(unchanged)'}\n"
        f"new tags: {', '.join(a.get('tags') or []) or '(unchanged)'}\n"
        f"new content:\n{a.get('content') or '(unchanged)'}"
    ),
)
async def note_update(ctx, args) -> str:
    note_id = args["note_id"]
    title = args.get("title")
    content = args.get("content")
    tags = args.get("tags")
    if title is None and content is None and tags is None:
        raise ValidationError("nothing to update: provide at least one of title/content/tags")
    note = await ctx.client.update_note(
        username=ctx.username,
        note_id=note_id,
        title=title,
        content=content,
        tags=tags,
    )
    if not note:
        return "update failed, note not found or no permission"
    return render.note_updated(note)


@tool(
    "note_delete",
    "Delete a note. Requires user confirmation.",
    {"type": "object", "properties": {"note_id": _NOTE_ID}, "required": ["note_id"]},
    requires_confirm=True,
    confirm_title="删除笔记",
    confirm_render=lambda a: f"note ID: {a.get('note_id')}\nThis note and its content will be permanently deleted.",
)
async def note_delete(ctx, args) -> str:
    note_id = args["note_id"]
    success = await ctx.client.delete_note(username=ctx.username, note_id=note_id)
    if success:
        return f"note {note_id[:8]}... deleted"
    return "delete failed, note not found or no permission"
