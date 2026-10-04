"""Agent REST API — backs the "browse" panel."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter

from beaver_agent import MainAgent, create_expert_agent, get_expert_agent_docs, get_expert_agent_names

logger = logging.getLogger("beaver_web")

router = APIRouter()


def _describe(agent) -> Dict[str, Any]:
    return {
        "class_name": agent.__class__.__name__,
        "description": (agent.__class__.__doc__ or "").strip(),
        "tools": sorted(agent.get_tool_names()),
    }


@router.get("/agents")
async def list_agents() -> Dict[str, Any]:
    """The main agent plus every expert agent it can delegate to.

    Instantiated rather than introspected so the reported tool list is exactly
    what the agent would be offered at runtime.
    """
    main = _describe(MainAgent())

    experts: List[Dict[str, Any]] = []
    docs = get_expert_agent_docs()
    for name in get_expert_agent_names():
        entry: Dict[str, Any] = {"name": name, "description": docs.get(name, "")}
        try:
            entry.update(_describe(create_expert_agent(name)))
        except Exception as e:  # noqa: BLE001 - one broken agent must not fail the list
            logger.warning("failed to describe expert agent %s: %s", name, e)
            entry.update({"class_name": name, "tools": [], "error": str(e)})
        experts.append(entry)

    return {"main": main, "experts": experts}
