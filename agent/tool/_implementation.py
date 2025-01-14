from typing import List

from phi.tools.toolkit import Toolkit

from agent.config import ToolConfig
from tools import tool_registry


def get_tools(config: ToolConfig) -> List[Toolkit]:
    tools = []
    for identifier in config.identifiers:
        tools.append(tool_registry.get_tool(identifier))

    return tools
