from agno.tools.toolkit import Toolkit

from agent.knowledge import KnowledgeConfig
from agent.tool.internal.query_knowledge_tool import QueryKnowledgeTool

from . import _config


def get_tools(
    tool_config: _config.ToolConfig, knowledge_config: KnowledgeConfig
) -> list[Toolkit]:
    from tools import tool_registry

    tools = []
    for identifier in tool_config.identifiers:
        tools.append(tool_registry.get_tool(identifier))

    # Add our own custom knowledge base search tool !!!
    tools.append(QueryKnowledgeTool(knowledge_config))

    return tools
