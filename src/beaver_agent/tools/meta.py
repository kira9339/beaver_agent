"""Miscellaneous tools."""

from __future__ import annotations

from datetime import datetime

from .registry import tool


@tool(
    "get_time",
    "Get the current local date and time of the server.",
    {"type": "object", "properties": {}, "required": []},
)
async def get_time(ctx, args) -> str:
    return f"current time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
