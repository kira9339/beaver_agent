"""Native function-calling tools for the Beaver agents.

Importing this package registers every tool (each module calls ``@tool`` at
import time). Agents then request a subset by name via ``get_tool_schemas``.
"""

from .context import ToolContext
from .registry import (
    TOOL_REGISTRY,
    ToolSpec,
    dispatch,
    get_tool_schemas,
    tool,
    tool_names,
)

# Import for the side effect of registering the tools.
from . import agent_creator, documents, meta, notes, preferences, reminders, sessions  # noqa: E402,F401

__all__ = [
    "ToolContext",
    "TOOL_REGISTRY",
    "ToolSpec",
    "dispatch",
    "get_tool_schemas",
    "tool",
    "tool_names",
]
