"""Native tool registry: OpenAI function-calling tools backed by BeaverCoreClient.

Everything the agent can do is declared here once, with its JSON Schema, its
confirmation policy and its handler. Agents then pick a *subset* by name, so
authorization stays explicit and auditable at the agent level.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence

from beaver_core.utils import ServiceError, ValidationError

from .context import ToolContext

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolSpec:
    """A single callable tool."""

    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable[[ToolContext, Dict[str, Any]], Awaitable[Any]]
    requires_confirm: bool = False
    confirm_title: str = ""
    # Renders the arguments into a human readable summary for the confirm dialog.
    confirm_render: Optional[Callable[[Dict[str, Any]], str]] = None


TOOL_REGISTRY: Dict[str, ToolSpec] = {}


def tool(
    name: str,
    description: str,
    parameters: Dict[str, Any],
    *,
    requires_confirm: bool = False,
    confirm_title: str = "",
    confirm_render: Optional[Callable[[Dict[str, Any]], str]] = None,
):
    """Register a tool handler.

    The decorated function must be ``async def handler(ctx, args) -> str``.
    Importing the module is what registers it, so ``tools/__init__.py`` imports
    every tool module.
    """

    def decorator(fn: Callable[[ToolContext, Dict[str, Any]], Awaitable[Any]]):
        if name in TOOL_REGISTRY:
            raise ValueError(f"duplicate tool name: {name}")
        TOOL_REGISTRY[name] = ToolSpec(
            name=name,
            description=description,
            parameters=parameters,
            handler=fn,
            requires_confirm=requires_confirm,
            confirm_title=confirm_title,
            confirm_render=confirm_render,
        )
        return fn

    return decorator


def tool_names() -> List[str]:
    """All registered tool names, sorted."""
    return sorted(TOOL_REGISTRY)


def get_tool_schemas(names: Sequence[str]) -> List[Dict[str, Any]]:
    """Build OpenAI function schemas for the requested tool names.

    Unknown names are skipped with a warning rather than raising, so a stale
    name in one agent cannot break the whole chat.
    """
    schemas: List[Dict[str, Any]] = []
    for n in names:
        spec = TOOL_REGISTRY.get(n)
        if spec is None:
            logger.warning("requested unknown tool %r; skipping", n)
            continue
        schemas.append({
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.parameters,
            },
        })
    return schemas


def _missing_required(spec: ToolSpec, args: Dict[str, Any]) -> List[str]:
    required = spec.parameters.get("required") or []
    return [k for k in required if args.get(k) in (None, "")]


async def dispatch(name: str, args: Dict[str, Any], ctx: ToolContext) -> str:
    """Execute a tool and always return a string.

    Never raises: a failure has to come back to the model as an observation it
    can react to, not as an exception that aborts the whole ReAct round.
    """
    spec = TOOL_REGISTRY.get(name)
    if spec is None:
        return f"tool {name} failed: unknown tool"

    if ctx.allowed_tools and name not in ctx.allowed_tools:
        return f"tool {name} failed: this agent is not authorized to use this tool"

    args = args or {}
    missing = _missing_required(spec, args)
    if missing:
        return f"tool {name} failed: missing required parameter(s): {', '.join(missing)}"

    try:
        if spec.requires_confirm:
            approved, reason = True, ""
            if ctx.confirm is not None:
                approved, reason = await ctx.confirm(spec, args)
            else:
                # No confirmation channel available (e.g. a script/tests):
                # fail closed rather than silently performing a write.
                return f"tool {name} failed: no confirmation channel is available"
            if not approved:
                if reason and reason.strip():
                    return ("user cancelled this operation and provided the following reason: "
                            + reason.strip())
                return "user cancelled this operation, please clarify user's intent"

        result = await spec.handler(ctx, args)
        if isinstance(result, str):
            return result
        return json.dumps(result, ensure_ascii=False, default=str)
    except ValidationError as e:
        return f"tool {name} failed: {e}"
    except ServiceError as e:
        return f"tool {name} failed: {e}"
    except Exception as e:  # noqa: BLE001 - must never escape into the ReAct loop
        logger.exception("tool %s failed", name)
        return f"tool {name} failed: {e.__class__.__name__}: {e}"
