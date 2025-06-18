import json
from functools import cached_property

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import tool

from agent.tool import ToolMetadata
from tools.square_tool._apis import list_catalog
from tools.square_tool.classes import (
    CatalogListResponse,
    ListCatalogInput,
    SquareAccessToken,
)
from utils.log import logger
from utils.secret import get_client_secret_with_fallback


class SquareTool(Toolkit):
    """
    Main Square Tool implementation for POS, payments, and catalog operations.
    """

    def __init__(
        self,
        tool_metadata: ToolMetadata,
        use_production: bool = False,
    ):
        super().__init__(name="square_tool")

        self.tool_metadata = tool_metadata
        self.use_production = use_production

        # Register tools
        self.register(self.list_catalog_tool)

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
    def list_catalog_tool(
        self,
    ) -> str:
        """
        List all catalog objects from Square's catalog API.

        Use this tool when customers ask about:
        - Menu items, food options, or available products
        - Item prices, descriptions, or variations
        - Categories, meal types, or menu sections
        - Available modifiers, add-ons, or customizations
        - Dietary information, ingredients, or allergens
        - Any general menu or catalog information inquiry

        This tool retrieves the complete restaurant catalog including items, categories,
        modifiers, pricing, and all related menu data from Square POS.

        Returns:
            str: A JSON-formatted string containing the complete catalog with items, categories,
                 variations, modifiers, prices, and all menu information
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
                cursor=input_data.cursor,
                types=input_data.types,
                catalog_version=input_data.catalog_version,
                use_production=input_data.use_production,
            )

            # Parse and validate response using pydantic model
            if isinstance(catalog_response, dict):
                response_model = CatalogListResponse(**catalog_response)
                return json.dumps(response_model.model_dump(), default=str)
            elif isinstance(catalog_response, list):
                # Handle case where response is a list
                response_model = CatalogListResponse(objects=catalog_response)
                return json.dumps(response_model.model_dump(), default=str)
            else:
                return json.dumps(catalog_response, default=str)

        except Exception as e:
            logger.error(f"[SquareTool.list_catalog_tool] Error listing catalog: {e}")
            return "Failed to list the catalog objects, please try again."
