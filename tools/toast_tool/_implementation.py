from functools import cached_property

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import tool

from agent.tool import ToolMetadata
from tools.toast_tool._apis import get_online_ordering_status
from tools.toast_tool._apis import get_store_info as get_store_info_api
from tools.toast_tool._apis import get_toast_access_token
from tools.toast_tool.classes import ToastAccessToken
from utils.log import logger
from utils.secret import get_client_secret_with_fallback


class ToastTool(Toolkit):
    def __init__(
        self,
        store_id: str,
        namespace: str,
        tool_metadata: ToolMetadata,
    ):
        super().__init__(name="toast_tool")

        self.store_id = store_id
        self.namespace = namespace
        self.tool_metadata = tool_metadata
        self._cached_store_info: str | None = None

        # Register tools
        self.register(self.check_online_ordering_status)
        self.register(self.get_store_info)
        self.register(self.checkout_order)
        self.register(self.check_address)

    @cached_property
    def _toast_bearer_token(self) -> ToastAccessToken | None:
        with LLMObs.task(name="get_adora_bearer_token"):
            api_key = get_client_secret_with_fallback("TOAST_QA_API_KEY")
            api_secret = get_client_secret_with_fallback("TOAST_QA_API_SECRET")
            bearer_token = get_toast_access_token(api_key, api_secret, True)
            return bearer_token

    @tool
    def get_store_info(self) -> str:
        """
        Retrieves detailed configuration information for a specific restaurant.

        Returns:
            str: A JSON-formatted string containing:
                - Basic restaurant information (e.g., name, timezone, GUID)
                - Location details such as address and phone number
                - Delivery and online ordering configuration
                - Operating hours and schedule data
                - Prep times and supported web URLs
        """

        try:
            # If store info is already cached return it
            if self._cached_store_info:
                return self._cached_store_info

            if not self._toast_bearer_token:
                return (
                    "Failed to authenticate ordering tool. "
                    "Please reach out to our support team at help@palona.ai "
                    "for assistance."
                )

            store_info = get_store_info_api(
                self._toast_bearer_token, self.store_id
            ).model_dump_json()

            # Cache store info
            self._cached_store_info = store_info
            return store_info

        except Exception as e:
            logger.error(f"[ToastTool.store_info] Error getting store info: {e}")
            return "Failed to get the store information, please try again."

    @tool
    def check_online_ordering_status(self) -> str:
        """
        Retrieves the current online ordering availability status of a specified restaurant.

        Returns:
            str: A JSON-formatted string containing:
            - The restaurant's online ordering availability status
            - The reason why the restaurant is available or unavailable to accept online orders
        """

        try:
            if not self._toast_bearer_token:
                return (
                    "Failed to authenticate ordering tool. Please reach out to our "
                    "support team at help@palona.ai for assistance."
                )

            status = get_online_ordering_status(
                self._toast_bearer_token, self.store_id, True
            ).model_dump_json()

            return status

        except Exception as e:
            logger.error(
                "[ToastTool.check_online_ordering_status] "
                f"Error in checking online ordering status: {e}"
            )
            return "Failed to check the online ordering status, please try again."

    @tool
    def checkout_order(self) -> str:
        """
        Processes an order checkout.

        Returns:
            str: Order checkout confirmation details
        """
        raise Exception("Not Implemented")

    @tool
    def check_address(self) -> str:
        """
        Validates a delivery address.

        Returns:
            str: Address validation results
        """
        raise Exception("Not Implemented")
