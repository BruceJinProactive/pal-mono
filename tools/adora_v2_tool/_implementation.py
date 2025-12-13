import asyncio
import threading

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs.decorators import tool

from agent.tool import ToolMetadata
from tools.adora_v2_tool._apis import (
    api_check_store_ordering_status,
    api_get_store_info,
    get_adora_pos_auth_token,
)
from tools.adora_v2_tool._utils import get_adora_credentials
from utils.log import logger


class AdoraV2Tool(Toolkit):
    def __init__(
        self,
        store_id: str,
        tool_metadata: ToolMetadata,
        **kwargs,
    ):
        super().__init__(name="adora_v2_tool")

        # Store configuration
        self.store_id = store_id
        self.tool_metadata = tool_metadata

        # Cache for bearer token with async lock
        self._cached_bearer_token: str | None = None
        self._token_lock = asyncio.Lock()

        # Log instance creation with built-in id
        instance_id = id(self)
        logger.debug(f"[AdoraV2Tool] Tool instance created: id={instance_id}")

        # Register tools
        self.register(self.check_store_ordering_status)
        self.register(self.get_store_info)
        self.register(self.check_address)

    async def _get_bearer_token(self) -> str | None:
        """Get cached bearer token or fetch new one if not cached."""
        logger.debug(
            f"[AdoraV2Tool._get_bearer_token] Thread: {threading.current_thread().name} (ID: {threading.current_thread().ident})"
        )

        async with self._token_lock:
            if self._cached_bearer_token:
                return self._cached_bearer_token

            api_key, api_secret = get_adora_credentials(
                self.tool_metadata.account_name or ""
            )
            if not api_key or not api_secret:
                logger.error("[AdoraV2Tool] Failed to retrieve Adora credentials")
                return None

            token = await get_adora_pos_auth_token(api_key, api_secret)
            if not token:
                logger.error(
                    "[AdoraV2Tool] Failed to retrieve bearer token from Adora API"
                )
                return None

            self._cached_bearer_token = token
            return self._cached_bearer_token

    @tool
    async def get_store_info(self, date: str) -> str:
        """
        Retrieves store details for the current date, including estimated wait times,
        business hours, and accepted payment methods.

        Args:
            date (str): The current date in yyyy-MM-dd format.

        Returns:
            str: Store details including store name, address, phone number, wait times,
                business hours, and payment methods.
        """
        logger.debug(
            f"[AdoraV2Tool.get_store_info] Thread: {threading.current_thread().name} (ID: {threading.current_thread().ident}), date: {date}"
        )

        bearer_token = await self._get_bearer_token()
        if not bearer_token:
            return "Failed to authenticate with Adora API."

        store_info_response = await api_get_store_info(
            bearer_token, self.store_id, date
        )
        if not store_info_response:
            return "Failed to retrieve store information."

        return str(store_info_response)

    @tool
    async def check_store_ordering_status(self) -> str:
        """
        Check the online ordering status of the store.

        Returns:
            str: The online ordering status of the store.
        """
        logger.debug(
            f"[AdoraV2Tool.check_store_ordering_status] Thread: {threading.current_thread().name} (ID: {threading.current_thread().ident})"
        )

        bearer_token = await self._get_bearer_token()
        if not bearer_token:
            return "Failed to authenticate with Adora API."

        status_response = await api_check_store_ordering_status(
            bearer_token, self.store_id
        )
        if not status_response:
            return "Failed to retrieve store status."

        is_online = status_response.get("isOnline", False)
        return f"Store online ordering status: {'Online' if is_online else 'Offline'}"

    @tool
    async def check_address(self, address: str) -> str:
        """
        This tool can be used to validate whether or not an address is within a
        delivery zone. Call this tool whenever you need to confirm if a certain
        delivery address can be delivered to.

        Args:
            address (str): A complete physical street address (e.g., "123 Main St, Springfield, IL 62704").
                This must not include phone numbers, names, or unrelated info.

        Returns:
            str: Validation result indicating if the address is within the delivery zone.
        """
        logger.debug(
            f"[AdoraV2Tool.check_address] Thread: {threading.current_thread().name} (ID: {threading.current_thread().ident}), address: {address}"
        )

        # Dummy implementation - simulate async behavior
        return f"Address validated: {address} is within the delivery zone."
