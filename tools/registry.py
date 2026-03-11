from typing import Dict, Optional, Type

from agno.tools.toolkit import Toolkit

from agent.tool import ToolIdentifier, ToolMetadata
from tools.adora_tool import AdoraTool
from tools.adora_v2_tool import AdoraV2Tool
from tools.catering_tool import CateringTool
from tools.livekit_tool import LiveKitTool
from tools.livekit_transfer_tool import LiveKitTransferTool
from tools.menusifu_tool import MenuSifuTool
from tools.minitable_tool import MiniTableTool
from tools.olo_tool import OloTool
from tools.opentable_tool import OpenTableTool
from tools.resy_tool import ResyTool
from tools.resy_tool_with_reservation import ResyToolWithReservation
from tools.square_tool import SquareTool
from tools.store_messaging_tool import StoreMessagingTool
from tools.toast_tool import ToastTool
from tools.vapi_tool import VapiTool
from tools.yelp_credit_card_tool import YelpCreditCardTool
from tools.yelp_no_credit_card_tool import YelpNoCreditCardTool
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
            "adora_tool": AdoraTool,
            "adora_v2_tool": AdoraV2Tool,
            "catering_tool": CateringTool,
            "toast_tool": ToastTool,
            "olo_tool": OloTool,
            "vapi_tool": VapiTool,
            "livekit_tool": LiveKitTool,
            "livekit_transfer_tool": LiveKitTransferTool,
            "yelp_tool": YelpTool,
            "yelp_credit_card_tool": YelpCreditCardTool,
            "yelp_no_credit_card_tool": YelpNoCreditCardTool,
            "square_tool": SquareTool,
            "store_messaging_tool": StoreMessagingTool,
            "opentable_tool": OpenTableTool,
            "resy_tool": ResyTool,
            "resy_tool_with_reservation": ResyToolWithReservation,
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
