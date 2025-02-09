from typing import Dict, Optional, Type

from phi.tools.toolkit import Toolkit

from .calculator_tool import CalculatorTool
from .adora_tool import AdoraTool


class ToolRegistry:
    """
    A registry that provides access to explicitly registered Phidata Toolkits.
    """

    def __init__(self):
        # TODO: Support non-Phidata tools
        self._tools: Dict[str, Type[Toolkit]] = {
            # Register available tools
            "calculator_tool": CalculatorTool,
            "adora_tool": AdoraTool,
        }

    def get_tool(self, name: str) -> Optional[Toolkit]:
        """
        Get a new instance of a toolkit by name.

        Args:
            name: The name of the toolkit to retrieve

        Returns:
            A new instance of the requested Toolkit, or None if not found
        """
        toolkit_class = self._tools.get(name)
        if toolkit_class:
            return toolkit_class()
        return None


tool_registry = ToolRegistry()
