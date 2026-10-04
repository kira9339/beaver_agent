import os
from datetime import datetime
from abc import ABC, abstractmethod
from typing import Optional, AsyncGenerator, List, Tuple, Dict, Any

from beaver_models import ModelConfig, ModelMessage, ModelRole, ModelResponse

class Agent(ABC):
    def __init__(self):
        self.history: List[ModelMessage] = []
        self.username: Optional[str] = None
        self.session_id: Optional[str] = None
        self.prompt_path: Optional[str] = None
        self._prompt_cache: Dict[str, Any] = {"mtime": None, "text": ""}

    @abstractmethod
    def get_tools(self) -> List[Dict[str, Any]]:
        """Return the OpenAI function schemas of the tools this agent may use."""

    def get_tool_names(self) -> set:
        """The names of the tools this agent is authorized to call.

        Used by the runtime as a whitelist so a hallucinated call cannot reach
        a tool the agent was never offered.
        """
        names = set()
        for schema in self.get_tools() or []:
            fn = schema.get("function") or {}
            if fn.get("name"):
                names.add(fn["name"])
        return names

    def get_system_prompt(self, prompt_path: str) -> str:
        """Return the system prompt"""
        try:
            mtime = os.path.getmtime(prompt_path)
            if self._prompt_cache["mtime"] != mtime:
                with open(prompt_path, "r", encoding="utf-8") as f:
                    self._prompt_cache["text"] = f.read().strip()
                self._prompt_cache["mtime"] = mtime
            return self._prompt_cache["text"]
        except Exception:
            raise RuntimeError(f"Failed to load system prompt from {prompt_path}")  

    def set_session_info(self, username: Optional[str], session_id: Optional[str]) -> None:
        self.username = username
        self.session_id = session_id

    def preprocess_input(self, text: str, add_time: bool = False) -> str:
        cleaned = (text or "").strip()
        cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")

        if len(cleaned) > 20000:
            raise ValueError("The length of the input cannot exceed 20000 characters")
        if add_time:
            processed = f"<time>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</time>\n{cleaned}"
        else:
            processed = cleaned
        return processed
