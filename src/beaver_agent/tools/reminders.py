"""Reminder tools."""

from __future__ import annotations

from datetime import datetime

from beaver_core.utils import ValidationError

from . import render
from .registry import tool

_REMINDER_ID = {"type": "string", "description": "The reminder ID, obtained from remind_list."}

_DUE_AT = {
    "type": "string",
    "description": (
        "When the reminder is due, formatted as 'YYYY-MM-DD HH:MM' in the server's local timezone "
        "(e.g. '2026-10-05 09:00'). Omit for a reminder with no due time."
    ),
}


def _parse_due_at(value: str) -> str:
    """Normalize 'YYYY-MM-DD HH:MM' (or an ISO string) to an ISO string."""
    text = (value or "").strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).isoformat()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text).isoformat()
    except ValueError:
        raise ValidationError(
            f"cannot parse due_at '{value}'; expected 'YYYY-MM-DD HH:MM'", field="due_at"
        )


@tool(
    "remind_add",
    "Create a reminder for the user. Requires user confirmation.",
    {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Short reminder title."},
            "body": {"type": "string", "description": "Optional longer description."},
            "due_at": _DUE_AT,
            "repeat_rule": {
                "type": "string",
                "enum": ["none", "daily", "weekly", "monthly"],
                "description": "Optional repeat rule. Use 'none' or omit for a one-off reminder.",
                "default": "none",
            },
        },
        "required": ["title"],
    },
    requires_confirm=True,
    confirm_title="创建提醒",
    confirm_render=lambda a: (
        f"title: {a.get('title', '')}\n"
        f"due at: {a.get('due_at') or 'none'}\n"
        f"repeat: {a.get('repeat_rule') or 'none'}\n"
        f"body: {a.get('body') or ''}"
    ),
)
async def remind_add(ctx, args) -> str:
    title = (args.get("title") or "").strip()
    if not title:
        raise ValidationError("title cannot be empty", field="title")
    repeat_rule = args.get("repeat_rule")
    if repeat_rule in (None, "", "none"):
        repeat_rule = None
    due_at = _parse_due_at(args["due_at"]) if args.get("due_at") else None
    reminder = await ctx.client.create_reminder(
        username=ctx.username,
        title=title,
        body=args.get("body") or "",
        due_at=due_at,
        repeat_rule=repeat_rule,
    )
    return render.reminder_created(reminder)


@tool(
    "remind_list",
    "List the user's reminders.",
    {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["pending", "completed", "cancelled"],
                "description": "Optional status filter. Omit to list reminders of every status.",
            },
            "limit": {"type": "integer", "default": 20},
        },
        "required": [],
    },
)
async def remind_list(ctx, args) -> str:
    reminders = await ctx.client.get_reminders(
        username=ctx.username,
        status=args.get("status"),
        limit=int(args.get("limit") or 20),
    )
    return render.reminders_list(reminders)


@tool(
    "remind_show",
    "Show the details of a single reminder.",
    {"type": "object", "properties": {"reminder_id": _REMINDER_ID}, "required": ["reminder_id"]},
)
async def remind_show(ctx, args) -> str:
    reminder = await ctx.client.get_reminder_with_id(args["reminder_id"])
    if not reminder:
        return "reminder not found"
    return render.reminder_detail(reminder)


@tool(
    "remind_done",
    "Mark a reminder as completed.",
    {"type": "object", "properties": {"reminder_id": _REMINDER_ID}, "required": ["reminder_id"]},
)
async def remind_done(ctx, args) -> str:
    reminder_id = args["reminder_id"]
    success = await ctx.client.update_reminder_status(reminder_id, ctx.username, "completed")
    if success:
        return f"reminder {reminder_id} marked as completed"
    return f"failed: reminder {reminder_id} not found or no permission"


@tool(
    "remind_delete",
    "Delete a reminder. Requires user confirmation.",
    {"type": "object", "properties": {"reminder_id": _REMINDER_ID}, "required": ["reminder_id"]},
    requires_confirm=True,
    confirm_title="删除提醒",
    confirm_render=lambda a: f"reminder ID: {a.get('reminder_id')}\nThis reminder will be permanently deleted.",
)
async def remind_delete(ctx, args) -> str:
    reminder_id = args["reminder_id"]
    success = await ctx.client.delete_reminder(reminder_id, ctx.username)
    return f"reminder {reminder_id} deleted" if success else f"delete failed: reminder {reminder_id} not found or no permission"
