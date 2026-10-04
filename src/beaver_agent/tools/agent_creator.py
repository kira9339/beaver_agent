"""The CreatorAgent's only write capability.

This is the single place where the agent can put new files on the server, so it
is deliberately narrow: a fixed target directory, a strict name grammar, a
source blacklist, and an import-verify-rollback cycle.
"""

from __future__ import annotations

import ast
import importlib
import logging
import re
from pathlib import Path
from typing import Tuple

from beaver_core.utils import ValidationError

from .registry import TOOL_REGISTRY, tool

logger = logging.getLogger(__name__)

# .../src/beaver_agent  — never derive this from os.getcwd(): the web server's
# working directory is not trustworthy.
AGENT_DIR = Path(__file__).resolve().parent.parent

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
_RESERVED = {"agent", "main", "creator", "creater", "tools"}

# Substrings that must not appear in generated source.
_FORBIDDEN = (
    "beaver_cli", "importlib", "subprocess", "os.system", "shutil",
    "eval(", "exec(", "__import__", "open(",
)

_MAX_PROMPT_CHARS = 20000
_MAX_CODE_CHARS = 20000


def _class_name(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_")) + "Agent"


def _resolve_paths(name: str) -> Tuple[Path, Path]:
    if not _NAME_RE.fullmatch(name or ""):
        raise ValidationError(
            "agent name must match ^[a-z][a-z0-9_]{1,40}$ (lowercase letters, digits, underscores)",
            field="name",
        )
    if name in _RESERVED:
        raise ValidationError(f"agent name '{name}' is reserved", field="name")

    py_path = (AGENT_DIR / f"{name}_agent.py").resolve()
    md_path = (AGENT_DIR / f"{name}_agent.md").resolve()
    for path in (py_path, md_path):
        if path.parent != AGENT_DIR:
            # Defensive: the name grammar already excludes separators.
            raise ValidationError("path escapes the agent directory", field="name")
    return py_path, md_path


def _validate_code(name: str, code: str) -> None:
    if not code or not code.strip():
        raise ValidationError("code cannot be empty", field="code")
    if len(code) > _MAX_CODE_CHARS:
        raise ValidationError(f"code exceeds {_MAX_CODE_CHARS} characters", field="code")

    lowered = code.lower()
    for snippet in _FORBIDDEN:
        if snippet in lowered:
            raise ValidationError(f"code must not contain '{snippet}'", field="code")

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise ValidationError(f"code is not valid Python: {e}", field="code")

    expected_class = _class_name(name)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != expected_class:
            continue
        bases = [
            b.id if isinstance(b, ast.Name) else (b.attr if isinstance(b, ast.Attribute) else "")
            for b in node.bases
        ]
        if not any("Agent" in b for b in bases):
            raise ValidationError(
                f"class {expected_class} must inherit from Agent", field="code"
            )
        if not any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "get_tools"
                   for n in node.body):
            raise ValidationError(
                f"class {expected_class} must define get_tools()", field="code"
            )
        return

    raise ValidationError(
        f"code must define a class named {expected_class} inheriting Agent", field="code"
    )


def _validate_prompt(prompt: str) -> None:
    if not prompt or not prompt.strip():
        raise ValidationError("prompt cannot be empty", field="prompt")
    if len(prompt) > _MAX_PROMPT_CHARS:
        raise ValidationError(f"prompt exceeds {_MAX_PROMPT_CHARS} characters", field="prompt")


def _rollback(py_path: Path, md_path: Path) -> None:
    py_path.unlink(missing_ok=True)
    md_path.unlink(missing_ok=True)
    importlib.invalidate_caches()
    from beaver_agent import _registry
    _registry._maybe_refresh_cache(force=True)


@tool(
    "create_expert_agent",
    "Create and register a new expert agent. Writes exactly two files into src/beaver_agent: "
    "<name>_agent.py and <name>_agent.md. Requires user confirmation.",
    {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Short lowercase agent name, e.g. 'recipe'. Must match ^[a-z][a-z0-9_]{1,40}$ and not already exist.",
            },
            "description": {
                "type": "string",
                "description": "One-line description, used as the class docstring and shown to the main agent.",
            },
            "code": {
                "type": "string",
                "description": (
                    "Full Python source of <name>_agent.py. Must define class <Name>Agent(Agent) with "
                    "get_tools() returning get_tool_schemas([...]) for the authorized tool names."
                ),
            },
            "prompt": {
                "type": "string",
                "description": "Full Markdown content of <name>_agent.md, the new agent's system prompt.",
            },
        },
        "required": ["name", "description", "code", "prompt"],
    },
    requires_confirm=True,
    confirm_title="创建专家 Agent",
    confirm_render=lambda a: (
        f"name: {a.get('name')}\n"
        f"description: {a.get('description')}\n"
        f"will create:\n  src/beaver_agent/{a.get('name')}_agent.py\n  src/beaver_agent/{a.get('name')}_agent.md\n"
        f"prompt preview:\n{(a.get('prompt') or '')[:400]}"
    ),
)
async def create_expert_agent(ctx, args) -> str:
    name = (args.get("name") or "").strip()
    code = args.get("code") or ""
    prompt = args.get("prompt") or ""

    py_path, md_path = _resolve_paths(name)
    if py_path.exists() or md_path.exists():
        return (
            f"create_expert_agent failed: '{name}_agent' already exists, "
            "please choose another name"
        )

    _validate_code(name, code)
    _validate_prompt(prompt)

    py_path.write_text(code, encoding="utf-8")
    md_path.write_text(prompt, encoding="utf-8")

    try:
        importlib.invalidate_caches()
        from beaver_agent import _registry

        _registry._maybe_refresh_cache(force=True)
        agent = _registry.create_expert_agent(name)
        schemas = agent.get_tools() or []
        if not schemas:
            raise ValueError("get_tools() returned no tools")
        unknown = {
            (s.get("function") or {}).get("name")
            for s in schemas
        } - set(TOOL_REGISTRY)
        unknown.discard(None)
        if unknown:
            raise ValueError(f"unknown tool name(s): {', '.join(sorted(unknown))}")
    except Exception as e:  # noqa: BLE001 - any failure must roll the files back
        logger.warning("generated agent %s failed to load: %s", name, e)
        _rollback(py_path, md_path)
        return f"create_expert_agent failed: generated agent could not be loaded: {e}"

    return (
        f"expert agent '{name}' created and registered.\n"
        f"python: {py_path}\n"
        f"prompt: {md_path}\n"
        f"tools: {', '.join(sorted((s.get('function') or {}).get('name') for s in schemas))}\n"
        f"it is now available through call_agent."
    )
