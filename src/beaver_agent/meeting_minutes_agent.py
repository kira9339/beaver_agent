import os
from typing import List, Dict, Any

from beaver_agent.agent import Agent
from beaver_agent.tools import get_tool_schemas

# Read-only: this agent must never modify, add or delete anything.
TOOL_NAMES = [
    "get_time",
    "note_list", "note_show", "note_search",
    "document_list", "document_search",
]


class MeetingMinutesAgent(Agent):
    """MeetingMinutesAgent: 会议记录员，负责查询、整理和总结会议笔记内容"""
    def __init__(self):
        super().__init__()
        self.prompt_path = os.path.join(os.path.dirname(__file__), "meeting_minutes_agent.md")

    def get_tools(self) -> List[Dict[str, Any]]:
        return get_tool_schemas(TOOL_NAMES)
