"""User preference tools."""

from __future__ import annotations

from beaver_core.utils import ValidationError

from . import render
from .registry import tool

_PREF_ID = {"type": "string", "description": "The preference ID, obtained from pref_list."}


@tool(
    "pref_add",
    "Save a user preference, so future conversations take it into account. Requires user confirmation.",
    {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "The preference, written as a short statement."},
            "confidential": {"type": "boolean", "description": "Mark the preference as confidential.", "default": False},
        },
        "required": ["text"],
    },
    requires_confirm=True,
    confirm_title="保存偏好",
    confirm_render=lambda a: (
        f"content: {a.get('text', '')}\n"
        f"confidential: {'yes' if a.get('confidential') else 'no'}"
    ),
)
async def pref_add(ctx, args) -> str:
    text = (args.get("text") or "").strip()
    if not text:
        raise ValidationError("text cannot be empty", field="text")
    pref = await ctx.client.add_preference(
        username=ctx.username,
        text=text,
        confidential=bool(args.get("confidential")),
    )
    return render.preference_added(pref)


@tool(
    "pref_list",
    "List the user's saved preferences.",
    {"type": "object", "properties": {}, "required": []},
)
async def pref_list(ctx, args) -> str:
    preferences = await ctx.client.get_preferences(ctx.username)
    return render.preferences_list(preferences)


@tool(
    "pref_merge",
    "Merge similar user preferences into consolidated ones. Requires user confirmation.",
    {"type": "object", "properties": {}, "required": []},
    requires_confirm=True,
    confirm_title="合并偏好",
    confirm_render=lambda a: "Merge highly similar preferences into consolidated entries.",
)
async def pref_merge(ctx, args) -> str:
    result = await ctx.client.merge_preferences(ctx.username)
    return render.merge_result(result, ctx.username)


@tool(
    "pref_delete",
    "Delete a saved preference. Requires user confirmation.",
    {"type": "object", "properties": {"preference_id": _PREF_ID}, "required": ["preference_id"]},
    requires_confirm=True,
    confirm_title="删除偏好",
    confirm_render=lambda a: f"preference ID: {a.get('preference_id')}",
)
async def pref_delete(ctx, args) -> str:
    preference_id = args["preference_id"]
    pref = await ctx.client.get_preference_by_id(ctx.username, preference_id)
    if not pref:
        return "preference not found or no permission"
    success = await ctx.client.delete_preference(ctx.username, preference_id)
    return f"preference {preference_id} deleted" if success else "delete failed, preference not found or no permission"
