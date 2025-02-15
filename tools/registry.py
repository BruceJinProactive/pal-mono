from typing import Dict, Optional, Type

from agno.tools.toolkit import Toolkit

# TODO: Absolute import required to resolve circular import. Fix this anti-pattern.
from agent.tool._config import ToolIdentifier
from tools.adora_tool import AdoraTool
from tools.calculator_tool import CalculatorTool


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
            if tool.args:
                return toolkit_class(**tool.args)

            return toolkit_class()

        return None


tool_registry = ToolRegistry()
