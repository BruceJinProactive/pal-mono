from typing import Dict, Optional, Type

from agno.tools.toolkit import Toolkit

# TODO: Absolute import required to resolve circular import. Fix this anti-pattern.
from agent.tool._config import ToolIdentifier, ToolMetadata
from tools.adora_tool import AdoraTool
from tools.booking_tool import BookingTool
from tools.calculator_tool import CalculatorTool
from tools.fashion_understanding_tools import FashionRecommendationLogicPipeline
from tools.toast_tool import ToastTool


class ToolRegistry:
    """
    A registry that provides access to explicitly registered Agno Toolkits.
    """

    def __init__(self):
        # TODO: Support non-Agno tools
        self._tools: Dict[str, Type[Toolkit]] = {
            # Register available tools
            "calculator_tool": CalculatorTool,
            "adora_tool": AdoraTool,
            "windsor_tool": FashionRecommendationLogicPipeline,
            "booking_tool": BookingTool,
            "toast_tool": ToastTool,
        }

    def get_tool(
        self, tool: ToolIdentifier, metadata: ToolMetadata
    ) -> Optional[Toolkit]:
        """
        Get a new instance of a toolkit by Tool Identifier object.

        Args:
            tool (ToolIdentifier): The details of the toolkit to retrieve
            metadata (ToolMetadata): Access agent metadata fields (e.g. agent_id, session_id, etc.)

        Returns:
            A new instance of the requested Toolkit, or None if not found
        """
        toolkit_class = self._tools.get(tool.tool_name)

        if toolkit_class:
            args = {}
            if tool.args:
                args = {**tool.args}

            if tool.access_metadata and metadata:
                args = {**args, "tool_metadata": metadata}

            if tool.client_config and tool.client_config.data:
                args = {**args, "client_config": tool.client_config}

            return toolkit_class(**args)

        return None


tool_registry = ToolRegistry()
