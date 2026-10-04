import os
from typing import List, Dict, Any

from beaver_agent.agent import Agent
from beaver_agent._registry import get_expert_agent_names, get_expert_agent_docs
from beaver_agent.tools import get_tool_schemas


class CreatorAgent(Agent):
    """Expert agent creator (CreatorAgent): Helps users create new expert agents"""
    def __init__(self):
        super().__init__()
        self.prompt_path = os.path.join(os.path.dirname(__file__), "creator_agent.md")

    def get_tools(self) -> List[Dict[str, Any]]:
        """Creator agent tools: create a new agent, then optionally talk to it."""
        names = [n for n in get_expert_agent_names() if n != "creator"]
        docs = get_expert_agent_docs()
        doc_lines = [f"- {n}: {docs.get(n, '')}".strip() for n in names] if names else []
        full_desc = "Switch to an expert agent" + ("\nOptional agents:\n" + "\n".join(doc_lines) if doc_lines else "")
        agent_name_prop = {"type": "string", "enum": names, "description": "names of expert agents"} if names else {"type": "string"}
        return get_tool_schemas(["create_expert_agent"]) + [
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
