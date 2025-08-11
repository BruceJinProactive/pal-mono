"""
MenuSifu Tool implementation
"""

from typing import Optional

from agno.tools.toolkit import Toolkit

from agent.tool import ToolMetadata


class MenuSifuTool(Toolkit):
    """
    MenuSifu Tool for retrieving restaurant menu information.
    """

    def __init__(
        self,
        merchant_id: str,
        tool_metadata: ToolMetadata,
        access_token: Optional[str] = None,
    ):
        super().__init__(name="menusifu_tool")

        self.tool_metadata = tool_metadata
        self.merchant_id = merchant_id
        self.access_token = access_token

        # Register tools
