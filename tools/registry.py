from typing import Dict, Optional, Type

from agno.tools.toolkit import Toolkit

# TODO: Absolute import required to resolve circular import. Fix this anti-pattern.
from agent.tool._config import ToolIdentifier, ToolMetadata
from tools.adora_tool import AdoraTool
from tools.booking_tool import BookingTool
from tools.calculator_tool import CalculatorTool
from tools.menusifu_tool import MenuSifuTool
from tools.minitable_tool import MiniTableTool
from tools.olo_tool import OloTool
from tools.opentable_tool import OpenTableTool
from tools.square_tool import SquareTool
from tools.toast_tool import ToastTool
from tools.vapi_tool import VapiTool
from tools.yelp_tool import YelpTool
from utils.log import logger


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
            "booking_tool": BookingTool,
            "toast_tool": ToastTool,
            "olo_tool": OloTool,
            "vapi_tool": VapiTool,
            "yelp_tool": YelpTool,
            "square_tool": SquareTool,
            "opentable_tool": OpenTableTool,
            "minitable_tool": MiniTableTool,
            "menusifu_tool": MenuSifuTool,
        }
        # Log instance creation with built-in id
        instance_id = id(self)
        logger.debug(f"ToolRegistry instance created: id={instance_id}")

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

            return toolkit_class(**args)

        return None


tool_registry = ToolRegistry()
