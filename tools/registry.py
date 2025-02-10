from typing import Dict, Optional, Type

from phi.tools.toolkit import Toolkit

# TODO: Absolute import required to resolve circular import. Fix this anti-pattern.
from agent.tool._config import ToolIdentifier
from tools.adora_tool import AdoraTool
from tools.calculator_tool import CalculatorTool

# TODO: Maybe it would be better to move ToolRegister to agent/tool/ ? (@kelvin)
# This would resolve a lot of cross import issues between tools/ and agent/tool
# Also, it makes sense to have the registry be in agent/tool/ since if we think about
# the agent as a human, a tool exists externally and is only "registered" / made known
# to the human when it is required to use it.
# We can do something like "adora_tool" would import the module from tools/adora_tool/


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
