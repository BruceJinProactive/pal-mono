from functools import cached_property
from typing import Optional

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import tool

from agent.tool import ToolMetadata
from tools.square_tool._apis import list_catalog
from tools.square_tool._utils import extract_customer_menu
from tools.square_tool.classes import ListCatalogInput, SquareAccessToken
from utils.log import logger
from utils.secret import get_client_secret_with_fallback


class SquareTool(Toolkit):
    """
    Main Square Tool implementation for POS, payments, and catalog operations.
    """

    def __init__(
        self,
        tool_metadata: Optional[ToolMetadata] = None,
        use_production: bool = False,
    ):
        super().__init__(name="square_tool")

        self.tool_metadata = tool_metadata
        self.use_production = use_production

        # Register tools
        self.register(self.list_catalog_customer_menu)

    @cached_property
    def _square_token(self) -> SquareAccessToken:
        """
        Retrieves and caches the Square API access token from environment variables.

        Returns:
            SquareAccessToken: An object containing the access token for Square API calls.

        Raises:
            ValueError: If the required environment variable is not set.
        """
        with LLMObs.task(name="get_square_token"):
            if self.use_production:
                api_key = get_client_secret_with_fallback(
                    "SQUARE_PRODUCTION_ACCESS_TOKEN"
                )
            else:
                api_key = get_client_secret_with_fallback("SQUARE_SANDBOX_ACCESS_TOKEN")

            bearer_token = SquareAccessToken(
                access_token=api_key,
                token_type="Bearer",
            )
            return bearer_token

    @tool
    def list_catalog_customer_menu(
        self,
    ) -> str:
        """
        Get a customer-friendly menu from Square catalog.

        Use this tool to show customers available menu items, prices, and dietary information.

        Returns:
            str: Customer-friendly food catalog information
        """
        try:
            # Ensure we can get the token
            token = self._square_token

            # Create input model for validation
            input_data = ListCatalogInput(
                cursor=None,
                types=None,
                catalog_version=None,
                use_production=self.use_production,
            )

            # Call the API function
            catalog_response = list_catalog(
                access_token=token,
                input_data=input_data,
            )

            # Return simple customer menu
            return extract_customer_menu(catalog_response)

        except Exception as e:
            logger.error(
                f"[SquareTool.list_catalog_customer_menu] Error getting menu: {e}"
            )
            return "Failed to get the menu, please try again."
