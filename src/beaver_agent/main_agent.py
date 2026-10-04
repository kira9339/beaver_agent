import os
from typing import Optional, Dict, Any, List

from beaver_agent.agent import Agent
from beaver_agent._registry import get_expert_agent_names, get_expert_agent_docs
from beaver_agent.tools import get_tool_schemas

# The main agent is the only one with the full tool set.
MAIN_TOOL_NAMES = [
    "get_time",
    "note_add", "note_list", "note_show", "note_search", "note_update", "note_delete",
    "remind_add", "remind_list", "remind_show", "remind_done", "remind_delete",
    "pref_add", "pref_list", "pref_merge", "pref_delete",
    "session_list", "session_show", "session_delete",
    "document_index", "document_list", "document_show", "document_search", "document_delete",
]


class MainAgent(Agent):
    """MainAgent: the main agent of the Beaver web app"""
    def __init__(self):
        super().__init__()
        self.prompt_path = os.path.join(os.path.dirname(__file__), "main_agent.md")

    def get_tools(self) -> List[Dict[str, Any]]:
        """Main session tool registry: general tools + expert invocation"""
        names = get_expert_agent_names()
        docs = get_expert_agent_docs()
        doc_lines = [f"- {n}: {docs.get(n, '')}".strip() for n in names] if names else []
        full_desc = "Switch to an expert agent" + ("\nOptional agents:\n" + "\n".join(doc_lines) if doc_lines else "")
        agent_name_prop = {"type": "string", "enum": names, "description": "names of expert agents"} if names else {"type": "string"}
        return get_tool_schemas(MAIN_TOOL_NAMES) + [
            {
                "type": "function",
                "function": {
                    "name": "call_agent",
                    "description": full_desc,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "agent_name": agent_name_prop,
                            "instruction": {"type": "string"}
                        },
                        "required": ["agent_name", "instruction"]
                    }
                }
            },
        ]
