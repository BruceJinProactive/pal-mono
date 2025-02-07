from typing import List

from phi.tools.toolkit import Toolkit

from tools import tool_registry

from . import _config


def get_tools(config: _config.ToolConfig) -> List[Toolkit]:
    tools = []
    for identifier in config.identifiers:
        tools.append(tool_registry.get_tool(identifier))

    return tools
