"""WebSocket event protocol for the Beaver web chat."""

from __future__ import annotations

from typing import Any, Dict

# Frontend -> backend
MSG_USER_MESSAGE = "user_message"
MSG_INTERRUPT = "interrupt"
MSG_CONFIRM_RESPONSE = "confirm_response"
MSG_PING = "ping"

# Backend -> frontend
EV_SESSION_CREATED = "session_created"
EV_TOKEN = "token"
EV_TOOL_START = "tool_start"
EV_TOOL_RESULT = "tool_result"
EV_CONFIRM_REQUEST = "confirm_request"
EV_AGENT_SWITCH = "agent_switch"
EV_MESSAGE_COMPLETE = "message_complete"
EV_SUMMARY = "summary"
EV_ERROR = "error"
EV_PONG = "pong"

# How long the backend waits for a confirmation before treating it as denied.
CONFIRM_TIMEOUT_MS = 120_000


def make_event(event_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Wrap a payload in the standard event envelope."""
    return {"type": event_type, "data": data}
