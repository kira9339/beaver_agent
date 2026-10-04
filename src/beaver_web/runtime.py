"""Event-driven ReAct runtime for the Beaver web chat.

The runtime owns the agent stack (MainAgent + expert agents) and the message
queue. A WebSocket connection sets ``send_event`` and calls ``enqueue`` to feed
user messages; the runtime drives the LLM/tool loop and emits events back.

Tools are native function calls dispatched through ``beaver_agent.tools``. Tools
that mutate data ask the user first, over the same WebSocket.
"""

from __future__ import annotations

import asyncio
import json
import logging
import textwrap
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from beaver_agent import MainAgent, create_expert_agent
from beaver_agent.agent import Agent
from beaver_agent.tools import ToolContext, ToolSpec, dispatch
from beaver_models import ModelMessage, ModelRole

from .protocol import (
    CONFIRM_TIMEOUT_MS,
    EV_AGENT_SWITCH,
    EV_CONFIRM_REQUEST,
    EV_ERROR,
    EV_MESSAGE_COMPLETE,
    EV_SESSION_CREATED,
    EV_SUMMARY,
    EV_TOKEN,
    EV_TOOL_RESULT,
    EV_TOOL_START,
    make_event,
)

logger = logging.getLogger("beaver_web")


def sanitize_history(history: List[ModelMessage]) -> List[ModelMessage]:
    """Drop tool_calls/tool messages that are not properly paired.

    A round can be cut short — the server restarts, the session is deleted, the
    page is refreshed while an expert agent is running — after the assistant
    message carrying ``tool_calls`` was persisted but before every tool result
    was. Replaying that verbatim makes the provider reject the whole request
    ("insufficient tool messages following tool_calls message"), which then
    wedges the session permanently. Repair it before sending instead.
    """
    cleaned: List[ModelMessage] = []
    i = 0
    total = len(history)

    while i < total:
        msg = history[i]

        # A tool message whose assistant tool_calls was dropped above.
        if msg.role == ModelRole.TOOL:
            i += 1
            continue

        tool_calls = (msg.metadata or {}).get("tool_calls") or []
        if msg.role != ModelRole.ASSISTANT or not tool_calls:
            cleaned.append(msg)
            i += 1
            continue

        expected = {tc.get("id") for tc in tool_calls if isinstance(tc, dict)}
        j = i + 1
        answered = set()
        while j < total and history[j].role == ModelRole.TOOL:
            call_id = (history[j].metadata or {}).get("tool_call_id")
            if call_id in expected:
                answered.add(call_id)
            j += 1

        if expected and answered == expected:
            cleaned.append(msg)
            cleaned.extend(history[i + 1:j])
        elif (msg.content or "").strip():
            # Keep what the assistant said; drop the call it never finished.
            cleaned.append(ModelMessage(role=msg.role, content=msg.content, metadata={}))
        i = j

    return cleaned


class WebAgentRuntime:
    """A single-session, event-driven ReAct loop.

    The runtime owns the agent stack (MainAgent + expert agents) and the message
    queue. A WebSocket connection sets ``send_event`` and calls ``enqueue`` to feed
    user messages; the runtime drives the LLM/tool loop and emits events back.
    """

    # Maximum number of nested expert agents (main -> expert -> expert).
    MAX_AGENT_DEPTH = 2

    def __init__(self, client, config, username: str, session_id: str, *, history: Optional[List[ModelMessage]] = None):
        self.client = client
        self.config = config
        self.username = username
        self.session_id = session_id

        self.main_agent = MainAgent()
        self.main_agent.set_session_info(username, session_id)
        if history:
            self.main_agent.history = list(history)

        self._agent_stack: List[tuple] = []  # [(agent_name, agent_instance)]
        self.queue: asyncio.Queue = asyncio.Queue()
        self.send_event = None  # async callable(event: dict), set by the WS handler
        self._task: Optional[asyncio.Task] = None
        self._interrupt_requested = False
        self.is_new = False
        # Set while a tool call is being handled, so a confirmation dialog can
        # be tied back to the matching tool card in the UI.
        self._current_tool_call_id: Optional[str] = None
        # confirm_id -> future resolving to (approved, reason).
        self._pending_confirms: Dict[str, asyncio.Future] = {}

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._react_loop())

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
    def enqueue(self, payload: "str | dict[str, Any]") -> None:
        """Queue an inbound message (plain text, or a pre-built envelope)."""
        message = {"type": "user_message", "content": payload} if isinstance(payload, str) else payload
        self.queue.put_nowait(message)

    def request_interrupt(self) -> None:
        """Stop the current generation.

        The interrupt flag is only checked inside the streaming token loop, so
        a pending confirmation has to be denied explicitly here — otherwise
        pressing "stop" while a dialog is open would do nothing.
        """
        self._interrupt_requested = True
        self._resolve_all_pending(False, "user interrupted")

    # -- user confirmation --------------------------------------------------

    def _resolve_all_pending(self, approved: bool, reason: str) -> None:
        for fut in list(self._pending_confirms.values()):
            if not fut.done():
                fut.set_result((approved, reason))
        self._pending_confirms.clear()

    def on_client_disconnected(self) -> None:
        """Deny anything awaiting confirmation when the socket goes away.

        The runtime survives disconnects, but the client will never see the
        pending ``confirm_request`` again after reconnecting, so leaving the
        future open would just stall the session until the timeout.
        """
        self._resolve_all_pending(False, "client disconnected before confirmation")

    def resolve_confirmation(self, confirm_id: str, approved: bool, reason: str = "") -> None:
        """Called by the WebSocket handler when the user answers a dialog."""
        fut = self._pending_confirms.get(confirm_id)
        if fut is not None and not fut.done():
            fut.set_result((bool(approved), reason or ""))

    async def _request_confirmation(self, spec: ToolSpec, args: Dict[str, Any]) -> Tuple[bool, str]:
        confirm_id = uuid.uuid4().hex
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending_confirms[confirm_id] = future

        summary = spec.confirm_render(args) if spec.confirm_render else json.dumps(
            args, ensure_ascii=False, indent=2
        )
        await self._emit(make_event(EV_CONFIRM_REQUEST, {
            "confirm_id": confirm_id,
            "tool_call_id": self._current_tool_call_id,
            "tool_name": spec.name,
            "title": spec.confirm_title or spec.name,
            "summary": summary,
            "arguments": args,
            "timeout_ms": CONFIRM_TIMEOUT_MS,
            "allow_reason": True,
        }))

        try:
            return await asyncio.wait_for(future, timeout=CONFIRM_TIMEOUT_MS / 1000)
        except asyncio.TimeoutError:
            await self._emit(make_event(EV_ERROR, {
                "message": "确认超时，操作已取消",
                "confirm_id": confirm_id,
            }))
            return False, "confirmation timed out, no response from the user"
        except asyncio.CancelledError:
            raise
        finally:
            self._pending_confirms.pop(confirm_id, None)

    async def _emit(self, event: Dict[str, Any]) -> None:
        if self.send_event is None:
            return
        try:
            await self.send_event(event)
        except Exception:
            logger.warning("failed to emit event %s", event.get("type"), exc_info=True)

    # -- main loop ----------------------------------------------------------

    async def _react_loop(self) -> None:
        while True:
            try:
                msg = await self.queue.get()
                msg_type = msg.get("type")

                if msg_type == "user_message":
                    text = msg.get("content", "")
                    if not text or not text.strip():
                        continue
                    await self._handle_user_input(self.main_agent, text, mode="main")

                # Unknown envelopes are logged and dropped; agent switching goes
                # through the call_agent tool, not through this queue.
                else:
                    logger.warning("Unknown message type in queue: %s", msg_type)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("react loop error")
                await self._emit(make_event(EV_ERROR, {"message": str(e)}))

    async def _ensure_conversation(self) -> None:
        """Create the conversation row on first use and tell the client its id.

        Deferred until now so that connecting (or just opening the page) does not
        leave an empty "new chat" behind.
        """
        if self.session_id:
            return
        conv = await self.client.create_conversation(
            self.username, title="new chat", metadata={"mode": "agent"}
        )
        self.session_id = conv.id
        self.is_new = True
        await self._emit(make_event(EV_SESSION_CREATED, {
            "session_id": conv.id,
            "title": conv.title,
            "created": True,
        }))

    async def _handle_user_input(self, agent: Agent, user_input: str, mode: str) -> None:
        stripped = user_input.strip()
        if stripped.lower() in ("/exit", "/quit", "exit", "quit"):
            await self._summary_end(agent)
            return
        if stripped.startswith("/"):
            # Slash commands other than exit are out of MVP scope; treat as a plain message.
            pass

        await self._ensure_conversation()
        await self.client.persist_message(
            self.session_id, ModelRole.USER, stripped,
            {"agent_name": agent.__class__.__name__},
        )
        await self._maybe_update_title(stripped)

        messages = await self._prepare_messages(agent, stripped)
        final_text = await self._send_and_receive(agent, messages, mode)
        if final_text:
            agent.history.append(ModelMessage(role=ModelRole.ASSISTANT, content=final_text or ""))

    async def _send_and_receive(self, agent: Agent, messages: List[ModelMessage], mode: str,
                                tool_choice: str = "auto") -> str:
        max_steps = 10
        steps = 0

        while steps < max_steps:
            # 每次循环重置变量（这正是 while 相对于递归需要特别小心的地方）
            token_usage_this_round = {"prompt": 0, "completion": 0}
            full_text = ""
            tool_calls: List[Dict[str, Any]] = []
            last_usage: Dict[str, int] = {}

            # ========= 核心 try 块：包裹本次“思考-行动”周期 =========
            try:
                # 1. 流式调用 AI
                async for ch in self.client.send_message_stream(
                        messages, tools=agent.get_tools(), tool_choice=tool_choice
                ):
                    # 中断检查（保留原有逻辑）
                    if self._interrupt_requested:
                        self._interrupt_requested = False
                        logger.info("interrupt requested, stopping generation")
                        break

                    if ch.is_final:
                        if ch.usage:
                            last_usage = ch.usage
                            token_usage_this_round["prompt"] += int(ch.usage.get("prompt_tokens", 0))
                            token_usage_this_round["completion"] += int(ch.usage.get("completion_tokens", 0))
                    else:
                        meta = ch.metadata or {}
                        tc = meta.get("tool_calls")
                        if tc:
                            tool_calls = tc
                        if ch.content:
                            full_text += ch.content
                            await self._emit(make_event(EV_TOKEN, {"content": ch.content}))

                total_tokens = last_usage.get("total_tokens")

                # 2. 分支一：无工具调用 -> 结束并返回
                if not tool_calls:
                    await self.client.persist_message(
                        self.session_id, ModelRole.ASSISTANT, full_text,
                        {"agent_name": agent.__class__.__name__, "usage": last_usage},
                        total_tokens,
                    )
                    await self._emit(make_event(EV_MESSAGE_COMPLETE, {
                        "tokens": token_usage_this_round,
                        "tool_calls": [],
                    }))
                    return full_text  # 正常结束

                # 3. 分支二：有工具调用 -> 保存并执行
                await self.client.persist_message(
                    self.session_id, ModelRole.ASSISTANT, full_text,
                    {"agent_name": agent.__class__.__name__, "usage": last_usage, "tool_calls": tool_calls},
                    total_tokens,
                )
                await self._handle_tool_calls(agent, messages, tool_calls, full_text, mode)
                steps += 1  # 步数加一，继续下一轮循环

            # ========= 异常捕获区 =========
            except asyncio.CancelledError:
                # 用户主动中断，向上传播，由 _react_loop 处理
                logger.info("send_and_receive cancelled during tool loop")
                raise
            except Exception as e:
                # 捕获 AI 调用异常、工具执行异常、网络超时等所有其他错误
                logger.exception("error in LLM/tool loop step")
                # 推送错误给前端
                await self._emit(make_event(EV_ERROR, {"message": f"处理出错: {str(e)}"}))
                # 关键：异常发生后立即终止循环，返回错误提示，而不是继续循环
                return f"抱歉，处理您的请求时出现错误：{str(e)}"

        # ========= 循环结束（超出最大步数）的处理 =========
        # 这里就是之前缺失的返回值！必须补上，否则返回 None 导致上层崩溃
        error_msg = f"工具调用超过最大限制 ({max_steps} 次)，已自动终止。"
        logger.warning(error_msg)
        await self._emit(make_event(EV_ERROR, {"message": error_msg}))
        return "抱歉，您的请求涉及过多的工具调用，系统已自动停止处理。"


    async def _handle_tool_calls(
        self,
        agent: Agent,
        messages: List[ModelMessage],
        tool_calls: List[Dict[str, Any]],
        assistant_text: str,
        mode: str,
    ) -> None:
        assistant_tool_intent = ModelMessage(
            role=ModelRole.ASSISTANT,
            content=assistant_text or "",
            metadata={"tool_calls": tool_calls},
        )## 根据 OpenAI 等主流 API 的规范，tool_calls 必须紧跟在 assistant 角色的消息之后，下一轮请求才能正常发送。如果不加，API 会报错或忽略工具结果。
        messages.append(assistant_tool_intent)
        agent.history.append(assistant_tool_intent)

        allowed_tools = agent.get_tool_names()

        for tc in tool_calls:
            fname = tc.get("function", {}).get("name")
            fargs_raw = tc.get("function", {}).get("arguments") or "{}"
            try:
                fargs = json.loads(fargs_raw) if isinstance(fargs_raw, str) else (fargs_raw or {})
            except Exception:
                fargs = {}

            await self._emit(make_event(EV_TOOL_START, {
                "tool_call_id": tc.get("id"),
                "name": fname,
                "arguments": fargs,
            }))
            start = time.monotonic()
            self._current_tool_call_id = tc.get("id")
            try:
                if fname == "call_agent":
                    tool_result = await self._handle_call_agent(fargs, agent, mode)
                else:
                    tool_result = await self._execute_tool_and_get_result(fname, fargs, allowed_tools)
            finally:
                self._current_tool_call_id = None
            duration_ms = int((time.monotonic() - start) * 1000)

            await self._emit(make_event(EV_TOOL_RESULT, {
                "tool_call_id": tc.get("id"),
                "name": fname,
                "result": str(tool_result),
                "duration_ms": duration_ms,
            }))

            tool_msg = ModelMessage(
                role=ModelRole.TOOL,
                content=str(tool_result),
                metadata={"tool_call_id": tc.get("id"), "name": fname},
            )
            messages.append(tool_msg)
            agent.history.append(tool_msg)
            await self.client.persist_message(
                self.session_id, ModelRole.TOOL, str(tool_result),
                {"agent_name": agent.__class__.__name__, "tool_call_id": tc.get("id"), "name": fname},
            )

    def _tool_context(self, allowed_tools) -> ToolContext:
        return ToolContext(
            client=self.client,
            username=self.username,
            session_id=self.session_id,
            allowed_tools=set(allowed_tools or ()),
            confirm=self._request_confirmation,
        )

    async def _execute_tool_and_get_result(self, name: str, args: Dict[str, Any],
                                           allowed_tools=None) -> str:
        """Run a native tool and return its textual observation.

        ``dispatch`` never raises: failures come back as readable strings the
        model can react to.
        """
        return await dispatch(name, args, self._tool_context(allowed_tools))

    async def _handle_call_agent(self, fargs: Dict[str, Any], agent: Agent, mode: str) -> str:
        """Delegate to an expert agent.

        From the main session this is unrestricted. From an expert session only
        CreatorAgent may branch out (to talk to the agent it just created), and
        nesting is capped so a misbehaving agent cannot recurse forever.
        """
        agent_name = fargs.get("agent_name")
        instruction = fargs.get("instruction")

        if mode == "main":
            return await self._expert_loop(agent_name, instruction=instruction)

        if agent.__class__.__name__ != "CreatorAgent":
            return "call_agent failed: this agent is not authorized to switch agents"
        if agent_name == agent.__class__.__name__:
            return "call_agent failed: cannot call self"
        if len(self._agent_stack) >= self.MAX_AGENT_DEPTH:
            return "call_agent failed: agent nesting limit reached"
        return await self._expert_loop(agent_name, instruction=instruction)

    # -- expert agent switching ---------------------------------------------

    async def _expert_loop(self, agent_name: Optional[str], instruction: Optional[str] = None) -> str:
        try:
            agent = create_expert_agent(agent_name)
        except Exception:
            return f"Unknown expert agent: {agent_name}"
        agent.set_session_info(self.username, self.session_id)

        await self._emit(make_event(EV_AGENT_SWITCH, {
            "from": self._agent_stack[-1][1].__class__.__name__ if self._agent_stack else "MainAgent",
            "to": agent.__class__.__name__,
        }))
        self._agent_stack.append((agent_name, agent))
        try:
            if instruction and instruction.strip():
                await self._handle_user_input(agent, instruction, mode="expert")
            while True:
                msg = await self.queue.get()
                if msg["type"] != "user_message":
                    continue
                text = msg.get("content", "")
                if not text or not text.strip():
                    continue
                if text.strip().lower() in ("exit", "quit", "/exit", "/quit"):
                    break
                await self._handle_user_input(agent, text, mode="expert")
        finally:
            if self._agent_stack and self._agent_stack[-1][1] is agent:
                self._agent_stack.pop()
            await self._emit(make_event(EV_AGENT_SWITCH, {
                "from": agent.__class__.__name__,
                "to": self._agent_stack[-1][1].__class__.__name__ if self._agent_stack else "MainAgent",
            }))
        return f"completed conversation with {agent.__class__.__name__} agent, switched back"

    # -- context building (ported from ChatAgents) --------------------------

    async def _prepare_messages(self, agent: Agent, user_input: str) -> List[ModelMessage]:
        sys_prompt = agent.get_system_prompt(agent.prompt_path)
        sys_context = await self._build_system_context(sys_prompt)
        processed_user_input = agent.preprocess_input(user_input, add_time=True)

        agent.history.append(ModelMessage(role=ModelRole.USER, content=processed_user_input))
        # Repair any round that an interruption left half-written, and keep the
        # repaired version so the junk does not accumulate turn after turn.
        agent.history = sanitize_history(agent.history)
        messages: List[ModelMessage] = [ModelMessage(role=ModelRole.SYSTEM, content=sys_context)]
        messages.extend(agent.history)
        return messages

    async def _build_system_context(self, sys_prompt: str) -> str:
        prefs_str = "none"
        pref_list = await self.client.get_preferences(self.username)
        if pref_list:
            prefs_str = "\n".join([f"- {p.text}" for p in pref_list])
##读取磁盘才需要异步操作，读取内存不需要
        reminds_str = "none"
        remind_list = await self.client.get_reminders(self.username, status="pending")
        if remind_list:
            reminds_str = "\n".join([f"- {r.title}.{r.body}" for r in remind_list])

        env_info = "\n".join([
            "<System Environment>",
            f"<Username>{self.username}</Username>",
            f"<Session ID>{self.session_id}</Session ID>",
            f"<Preferences>{prefs_str}</Preferences>",
            f"<Reminders>{reminds_str}</Reminders>",
            "</System Environment>",
        ])
        return f"{sys_prompt}\n\n{env_info.strip()}"

    async def _summary_end(self, agent: Agent) -> str:
        """Generate a conversation summary and emit it (non-streaming)."""
        if not self.session_id:
            return ""
        summary_prompt = textwrap.dedent("""\
            <system>
            This conversation with the user is about to end. Please generate a concise summary in the first person perspective based on the dialogue history.
            In the current state, you are not allowed to call any tools.
            Do not add any opening remarks, directly generate the conversation summary.
            </system>"""
        )
        messages = await self._prepare_messages(agent, summary_prompt)
        full_text = ""
        # tool_choice is only sent when tools are present: some OpenAI-compatible
        # providers reject a tool_choice with an empty tool list.
        async for ch in self.client.send_message_stream(messages):
            if not ch.is_final and ch.content:
                full_text += ch.content
        await self.client.update_conversation(self.username, self.session_id, summary=full_text)
        await self._emit(make_event(EV_SUMMARY, {"content": full_text}))
        return full_text

    async def _maybe_update_title(self, user_input: str) -> None:
        if not self.session_id:
            return
        conv = await self.client.get_conversation(self.session_id, self.username)
        if conv and (conv.title or "").strip() in ("", "new chat"):
            await self.client.update_conversation(self.username, self.session_id, title=user_input[:8])
