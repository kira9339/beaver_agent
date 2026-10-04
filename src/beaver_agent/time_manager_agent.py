import os
from typing import List, Dict, Any

from beaver_agent.agent import Agent
from beaver_agent.tools import get_tool_schemas

# Authorized scope, matching the prompt: log notes, set reminders, keep preferences.
TOOL_NAMES = [
    "get_time",
    "note_add", "note_list", "note_show", "note_search", "note_delete",
    "remind_add", "remind_list", "remind_show", "remind_done", "remind_delete",
    "pref_add", "pref_list", "pref_delete",
]


class TimeManagerAgent(Agent):
    """TimeManagerAgent: Help users manage time, schedule, and plans"""
    def __init__(self):
        super().__init__()
        self.prompt_path = os.path.join(os.path.dirname(__file__), "time_manager_agent.md")

    def get_tools(self) -> List[Dict[str, Any]]:
        """TimeManagerAgent tools"""
        return get_tool_schemas(TOOL_NAMES)
