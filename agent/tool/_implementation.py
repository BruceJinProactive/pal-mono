from agno.tools.toolkit import Toolkit

from agent.knowledge import KnowledgeConfig
from agent.tool.internal.query_knowledge_tool import QueryKnowledgeTool
from agent.tool.internal.query_messages_tool import QueryMessagesTool
from utils.log import logger

from . import _config


def get_tools(
    tool_config: _config.ToolConfig, knowledge_config: KnowledgeConfig
) -> list[Toolkit]:
    from tools import tool_registry

    tools = []
    for identifier in tool_config.identifiers:
        try:
            tools.append(tool_registry.get_tool(identifier, tool_config.metadata))
        except Exception:
            logger.exception(f"Tool {identifier} failed to load.")

    if knowledge_config.enabled:
        # Add our own custom knowledge base search tool !!!
        tools.append(QueryKnowledgeTool(knowledge_config))

    tools.append(QueryMessagesTool(tool_config.metadata))

    return tools
