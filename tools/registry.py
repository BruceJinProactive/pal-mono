from typing import Dict, Optional, Type

from agno.tools.toolkit import Toolkit

# TODO: Absolute import required to resolve circular import. Fix this anti-pattern.
from agent.tool._config import ToolIdentifier
from tools.adora_tool import AdoraTool
from tools.booking_tool import BookingTool
from tools.calculator_tool import CalculatorTool
from tools.fashion_understanding_tools import FashionRecommendationLogicPipeline


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
        }

    def get_tool(self, tool: ToolIdentifier) -> Optional[Toolkit]:
        """
        Get a new instance of a toolkit by Tool Identifier object.

        Args:
            tool (ToolIdentifier): The details of the toolkit to retrieve

        Returns:
            A new instance of the requested Toolkit, or None if not found
        """
        toolkit_class = self._tools.get(tool.tool_name)

        if toolkit_class:
            args = {}
            if tool.args:
                args = {**tool.args}

            if tool.access_metadata and tool.metadata:
                args = {**args, **tool.metadata.model_dump()}

            if tool.client_config and tool.client_config.data:
                args = {**args, **tool.client_config.model_dump(by_alias=True)}

            return toolkit_class(**args)

        return None


tool_registry = ToolRegistry()
