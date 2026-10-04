"""FastAPI application entry point for the Beaver web layer."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from beaver_client import BeaverConfig, BeaverCoreClient

from . import deps
from .api import agents as agents_api
from .api import config as config_api
from .api import documents, sessions, users
from .protocol import (
    EV_ERROR,
    EV_PONG,
    EV_SESSION_CREATED,
    MSG_CONFIRM_RESPONSE,
    MSG_INTERRUPT,
    MSG_PING,
    MSG_USER_MESSAGE,
    make_event,
)
from .session_manager import ChatSessionManager

logger = logging.getLogger("beaver_web")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Reuse the exact config + facade the CLI uses, so web and CLI share the same
    # model provider, SQLite database and Chroma vector store.
    config = BeaverConfig()
    client = BeaverCoreClient(config)
    manager = ChatSessionManager(client, config)
    deps.init_app_state(client, manager)
    logger.info("BeaverCoreClient initialized (user=%s, provider=%s)",
                config.get_current_username(), config.model_provider.provider)

    # Load the local embedding model in the background rather than inline: it
    # takes tens of seconds, and doing it here would delay the server coming up.
    # Keep a reference on app.state so the task is not garbage collected.
    app.state.warmup_task = asyncio.create_task(client.warm_up())
    yield


app = FastAPI(title="Beaver Web", version="0.1.0", lifespan=lifespan)

# H5 dev server runs on a different origin, so allow cross-origin requests.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(config_api.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(agents_api.router, prefix="/api")


@app.websocket("/ws/chat/{session_id}")
async def ws_chat(websocket: WebSocket, session_id: str, username: str = Query(...)):
    await websocket.accept()
    manager = deps.get_manager()
    runtime, created = await manager.get_or_create(username, session_id)

    async def send_event(event: Dict[str, Any]) -> None:
        await websocket.send_json(event)

    runtime.send_event = send_event

    # session_id is empty for a chat that has not been used yet: the runtime
    # creates the conversation on the first message and re-announces it.
    conv = None
    if runtime.session_id:
        conv = await deps.get_client().get_conversation(runtime.session_id, username)
    await send_event(make_event(EV_SESSION_CREATED, {
        "session_id": runtime.session_id,
        "title": conv.title if conv else "new chat",
        "created": created,
    }))

    if runtime._task is None or runtime._task.done():
        runtime.start()

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            msg_data = data.get("data") or {}
            if msg_type == MSG_USER_MESSAGE:
                runtime.enqueue(msg_data.get("content", ""))
            elif msg_type == MSG_INTERRUPT:
                runtime.request_interrupt()
            elif msg_type == MSG_CONFIRM_RESPONSE:
                # Routed straight to the pending future, never through the
                # user-message queue (that would race with real input).
                runtime.resolve_confirmation(
                    msg_data.get("confirm_id", ""),
                    msg_data.get("approved", False),
                    msg_data.get("reason", "") or "",
                )
            elif msg_type == MSG_PING:
                await send_event(make_event(EV_PONG, {}))
    except WebSocketDisconnect as exc:
        logger.info("ws disconnected: session=%s user=%s code=%s reason=%s",
                    runtime.session_id, username, getattr(exc, "code", "?"), getattr(exc, "reason", ""))
    except Exception as e:
        logger.exception("ws error")
        try:
            await send_event(make_event(EV_ERROR, {"message": str(e)}))
        except Exception:
            pass
    finally:
        runtime.on_client_disconnected()
        # A chat that never got a message has nothing to preserve, and keeping it
        # would leak its pending key. Runtimes with a conversation stay alive so a
        # refresh can reconnect to them.
        await manager.drop_if_unused(runtime)


# Serve the built uni-app H5 frontend as static files when present.
_frontend_dist = Path(__file__).parent / "frontend" / "dist" / "build" / "h5"
if _frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")


def main() -> None:
    import os

    import uvicorn

    # Reload is opt-in (BEAVER_RELOAD=1). The CreatorAgent writes new expert agents
    # into src/beaver_agent/ at runtime, and a reloader watching the source tree
    # would restart the server mid-conversation — dropping the WebSocket and
    # cancelling the agent loop halfway through a tool call.
    reload_enabled = os.getenv("BEAVER_RELOAD", "").lower() in ("1", "true", "yes")

    # Bound to localhost by default: the app has a username-only login model
    # (no passwords), and /api/config exposes the server's provider settings.
    uvicorn.run(
        "beaver_web.app:app",
        host=os.getenv("BEAVER_HOST", "127.0.0.1"),
        port=int(os.getenv("BEAVER_PORT", "8000")),
        reload=reload_enabled,
        reload_excludes=[
            "src/beaver_agent/*",
            "uploads/*",
            "chroma_db/*",
            "logs/*",
            "*.db",
        ] if reload_enabled else None,
    )


if __name__ == "__main__":
    main()
