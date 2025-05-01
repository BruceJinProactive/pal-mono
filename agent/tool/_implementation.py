from agno.tools.toolkit import Toolkit

from agent.knowledge import KnowledgeConfig
from agent.memory import MemoryConfig
from agent.tool.internal.memory_tool import MemoryTool
from agent.tool.internal.query_knowledge_tool import QueryKnowledgeTool
from agent.tool.internal.query_messages_tool import QueryMessagesTool
from utils.log import logger

from . import _config


def get_tools(
    tool_config: _config.ToolConfig,
    knowledge_config: KnowledgeConfig,
    memory_config: MemoryConfig,
    user_id: str,
) -> list[Toolkit]:
    """
    Creates a list of tools for the agent based on provided configurations.

    Args:
        tool_config: Configuration for general tools
        knowledge_config: Configuration for knowledge base access (enabled/disabled)
        memory_config: Configuration for memory access (enabled/disabled)
        user_id: The user ID for user-specific tools

    Returns:
        A list of tool instances to be used by the agent
    """
    from tools import tool_registry

    tools = []
    for identifier in tool_config.identifiers:
        try:
            tools.append(tool_registry.get_tool(identifier, tool_config.metadata))
        except Exception:
            logger.exception(f"Tool {identifier} failed to load.")

    # Add memory tool if enabled in memory configuration
    if memory_config.enabled:
        tools.append(MemoryTool(user_id=user_id))

    # Add knowledge tool if enabled in knowledge configuration
    if knowledge_config.enabled:
        tools.append(QueryKnowledgeTool(knowledge_config))

    # Always add QueryMessagesTool (not configurable)
    tools.append(QueryMessagesTool(tool_config.metadata))

    return tools
