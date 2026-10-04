"""Manages active WebAgentRuntime instances, keyed by session id."""

from __future__ import annotations

import logging
import uuid
from typing import Dict, Optional, Tuple

from .runtime import WebAgentRuntime

logger = logging.getLogger("beaver_web")

# Prefix for runtimes whose conversation does not exist yet.
_PENDING = "pending:"


class ChatSessionManager:
    """Maps session_id -> WebAgentRuntime.

    Runtimes survive WebSocket disconnects so a page refresh can reconnect to the
    same in-progress conversation. They are removed on explicit session delete,
    when a client leaves a never-used chat, or on server shutdown (LRU/idle
    eviction is future work).

    A conversation row is **not** created when a client merely connects: every
    visit would otherwise leave an empty "new chat" behind, which makes deleting
    sessions look like it has no effect. The runtime creates the row on the first
    message instead (``WebAgentRuntime._ensure_conversation``), and until then it
    is held under a ``pending:<uuid>`` key.
    """

    def __init__(self, client, config):
        self.client = client
        self.config = config
        self._runtimes: Dict[str, WebAgentRuntime] = {}

    def _find(self, session_id: str) -> Optional[WebAgentRuntime]:
        """Look up by key, then by the conversation the runtime ended up owning."""
        runtime = self._runtimes.get(session_id)
        if runtime is not None:
            return runtime
        for candidate in self._runtimes.values():
            if candidate.session_id and candidate.session_id == session_id:
                return candidate
        return None

    def _rekey(self, runtime: WebAgentRuntime, session_id: str) -> None:
        for key in [k for k, v in self._runtimes.items() if v is runtime and k != session_id]:
            self._runtimes.pop(key, None)
        self._runtimes[session_id] = runtime

    async def get_or_create(self, username: str, session_id: str) -> Tuple[WebAgentRuntime, bool]:
        """Return (runtime, created).

        ``created`` is True only when the caller should treat this as a brand new
        chat. Reuses a live runtime when one exists, otherwise rebuilds it from
        the stored transcript.
        """
        if session_id and session_id not in ("new", "None"):
            runtime = self._find(session_id)
            if runtime is not None:
                # Was created under a pending key and has since got its row.
                self._rekey(runtime, session_id)
                return runtime, False
            # Verify the session belongs to this user before reattaching.
            conv = await self.client.get_conversation(session_id, username)
            if conv is not None:
                messages = await self.client.get_conversation_messages(session_id, username)
                runtime = WebAgentRuntime(
                    self.client, self.config, username, session_id, history=messages
                )
                runtime.is_new = False
                self._runtimes[session_id] = runtime
                return runtime, False

        # Fresh chat: hold the runtime without touching the database yet.
        key = f"{_PENDING}{uuid.uuid4().hex}"
        runtime = WebAgentRuntime(self.client, self.config, username, "")
        runtime.is_new = True
        self._runtimes[key] = runtime
        logger.info("created pending runtime %s (user %s)", key, username)
        return runtime, True

    def swap_client(self, client) -> None:
        """Re-point this manager and every live runtime at a new client.

        Used when the model configuration changes, so sessions that are already
        open pick up the new provider instead of holding the stale one.
        """
        self.client = client
        for runtime in self._runtimes.values():
            runtime.client = client

    def get(self, session_id: str) -> Optional[WebAgentRuntime]:
        return self._find(session_id)

    async def remove(self, session_id: str) -> None:
        runtime = self._find(session_id)
        if runtime is None:
            return
        for key in [k for k, v in self._runtimes.items() if v is runtime]:
            self._runtimes.pop(key, None)
        await runtime.stop()

    async def drop_if_unused(self, runtime: WebAgentRuntime) -> None:
        """Forget a runtime that never started a conversation.

        Called when a client disconnects: the runtime has nothing worth keeping
        alive, and leaving it would leak its ``pending:`` key.
        """
        if runtime.session_id:
            return
        for key in [k for k, v in self._runtimes.items() if v is runtime]:
            self._runtimes.pop(key, None)
        await runtime.stop()

    def list_active(self) -> list:
        return list(self._runtimes.keys())
