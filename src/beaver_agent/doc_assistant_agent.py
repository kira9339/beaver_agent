import os
from typing import List, Dict, Any
from beaver_agent.agent import Agent
from beaver_agent.tools import get_tool_schemas


class DocAssistantAgent(Agent):
    """DocAssistantAgent: 个人文档助手，在用户上传的文档知识库中快速检索、定位并精准回答，只读不修改。"""

    def __init__(self):
        super().__init__()
        self.prompt_path = os.path.join(os.path.dirname(__file__), "doc_assistant_agent.md")

    def get_tools(self) -> List[Dict[str, Any]]:
        return get_tool_schemas(["get_time", "document_list", "document_show", "document_search"])
