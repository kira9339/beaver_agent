"""Execution context handed to every tool handler."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Optional, Set, Tuple

if TYPE_CHECKING:  # pragma: no cover - typing only
    from beaver_client import BeaverCoreClient

    from .registry import ToolSpec

# Signature of the confirmation callback injected by the runtime.
# Returns (approved, reason).
ConfirmFn = Callable[["ToolSpec", dict], Awaitable[Tuple[bool, str]]]


@dataclass
class ToolContext:
    """Everything a tool handler needs, without reaching for globals.

    ``allowed_tools`` is the whitelist of the agent that is currently running.
    ``dispatch`` re-checks it so a hallucinated call cannot exceed the agent's
    authorization even though the schema was never offered.
    """

    client: "BeaverCoreClient"
    username: str
    session_id: str
    allowed_tools: Set[str] = field(default_factory=set)
    confirm: Optional[ConfirmFn] = None
