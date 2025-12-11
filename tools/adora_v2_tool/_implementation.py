import threading

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs.decorators import tool

from utils.log import logger


class AdoraV2Tool(Toolkit):
    def __init__(self):
        super().__init__(name="adora_v2_tool")

        # Log instance creation with built-in id
        instance_id = id(self)
        logger.debug(f"AdoraV2 Tool instance created: id={instance_id}")

        # Register tools
        self.register(self.check_online_ordering_status)
        self.register(self.get_store_info)
        self.register(self.check_address)

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
            f"get_store_info called with date: {date} on thread: {threading.current_thread().name} (ID: {threading.current_thread().ident})"
        )

        # Dummy implementation - simulate async behavior
        return f"Store info retrieved for date: {date}"

    @tool
    async def check_online_ordering_status(self) -> str:
        """
        Check the online ordering status of the store.

        Args:
            None

        Returns:
            str: The online ordering status of the store.
        """
        logger.debug(
            f"check_online_ordering_status called on thread: {threading.current_thread().name} (ID: {threading.current_thread().ident})"
        )

        # Dummy implementation - simulate async behavior
        return "The store is open for online ordering."

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
            f"check_address called with address: {address} on thread: {threading.current_thread().name} (ID: {threading.current_thread().ident})"
        )

        # Dummy implementation - simulate async behavior
        return f"Address validated: {address} is within the delivery zone."
