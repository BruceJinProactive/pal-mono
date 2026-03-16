from agno.tools.toolkit import Toolkit

from agent.knowledge import KnowledgeConfig
from agent.tool.internal.query_knowledge_tool import QueryKnowledgeTool
from agent.tool.internal.query_messages_tool import QueryMessagesTool
from utils.log import logger

from . import _config


def get_tools(
    tool_config: _config.ToolConfig,
    knowledge_config: KnowledgeConfig,
    user_id: str,
) -> list[Toolkit]:
    """
    Creates a list of tools for the agent based on provided configurations.

    Args:
        tool_config: Configuration for general tools
        knowledge_config: Configuration for knowledge base access (enabled/disabled)
        user_id: The user ID for user-specific tools

    Returns:
        A list of tool instances to be used by the agent
    """
    from tools import tool_registry

    tools = []
    for identifier in tool_config.identifiers:
        try:
            tool = tool_registry.get_tool(identifier, tool_config.metadata)
            if tool is None:
                logger.warning(
                    f"[get_tools] Tool '{identifier.tool_name}' not found in registry, skipping"
                )
            else:
                arg_keys = list((identifier.args or {}).keys())
                logger.debug(
                    f"[get_tools] Loaded tool '{identifier.tool_name}' with args: {arg_keys}"
                )
                tools.append(tool)
        except Exception:
            logger.exception(f"Tool {identifier} failed to load.")

    # Add knowledge tool if enabled in knowledge configuration
    if knowledge_config.enabled:
        tools.append(QueryKnowledgeTool(knowledge_config))

    # Always add QueryMessagesTool (not configurable)
    tools.append(QueryMessagesTool(tool_config.metadata))

    return tools
