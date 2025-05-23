import os
from functools import cached_property

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import tool

from agent.tool import ToolMetadata
from agent.tool.internal.query_messages_tool import QueryMessagesTool
from tools.olo_tool._apis import get_store_info
from tools.olo_tool.classes import OloAccessToken
from utils.log import logger
from utils.ordering._query_engine import create_query_engine


class OloTool(Toolkit):
    def __init__(
        self,
        store_id: str,
        namespace: str,
        index_name: str,
        tool_metadata: ToolMetadata,
    ):
        super().__init__(name="olo_tool")

        self.store_id = store_id
        self.namespace = namespace
        self.index_name = index_name
        self.tool_metadata = tool_metadata
        self._cached_store_info: str | None = None

        # Register tools

        # Retrieval tools
        self.query_messages_tool = QueryMessagesTool(self.tool_metadata)
        self.query_engine = create_query_engine(
            namespace=self.namespace, index_name=self.index_name
        )

    @cached_property
    def _olo_token(self) -> OloAccessToken:
        """
        Retrieves and caches the Olo API access token from environment variables.

        Returns:
            OloAccessToken: An object containing the access token for Olo API calls.

        Raises:
            ValueError: If the required environment variable is not set.
        """
        with LLMObs.task(name="get_olo_token"):
            api_key = os.getenv("OLOSANDBOX_API_KEY")
            if not api_key:
                logger.error("OLOSANDBOX_API_KEY environment variable not set")
                raise ValueError("Olo API key environment variable not set")
            bearer_token = OloAccessToken(
                access_token=api_key,
                token_type="OloKey",
            )
            return bearer_token

    @tool
    def get_store_info_tool(self) -> str:
        """
        Retrieves detailed configuration information for a specific restaurant.

        Returns:
            str: A JSON-formatted string containing OloStore object
        """

        try:
            # If store info is already cached return it
            if self._cached_store_info:
                return self._cached_store_info

            if not self._olo_token:
                return (
                    "Failed to authenticate Olo ordering tool. "
                    "Please reach out to our support team at help@palona.ai "
                    "for assistance."
                )

            # Get store info from Olo
            store_info = get_store_info(
                int(self.store_id), self._olo_token
            ).model_dump_json()

            # Cache store info for future use
            self._cached_store_info = store_info
            return store_info

        except Exception as e:
            logger.error(f"[OloTool.store_info] Error getting store info: {e}")
            return "Failed to get the store information, please try again."
