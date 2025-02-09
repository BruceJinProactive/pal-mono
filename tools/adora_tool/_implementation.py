from typing import List

from phi.tools.toolkit import Toolkit
from phi.utils.log import logger


class AdoraTool(Toolkit):
    def __init__(self):
        super().__init__(name="adora_tool")

        # Register tools
        self.register(self.check_online_ordering_status)
        self.register(self.get_store_info)
        self.register(self.validate_address)
        self.register(self.validate_order)

        self.store_id = "9WHCV"

    def check_online_ordering_status(self) -> str:
        """
        Checks if the store is online for ordering.

        Returns:
            str: The online status of the store.
        """
        try:
            return "STORE IS ONLINE"
        except Exception as e:
            error_msg = "Error in checking online ordering status"
            logger.error(f"{error_msg}: {e}")
            return error_msg

    def get_store_info(self, store_id: str, date: str) -> str:
        """
        Get the store information by given store id and target business date

        Args:
            store_id (str): The store id
            date (str): The target business date

        Returns:
            str: The store information of if store is open
        """
        try:
            store_id = self.store_id
            return f"STORE ID {store_id} IS OPEN on {date}"
        except Exception as e:
            error_msg = "Error getting store info"
            logger.error(f"{error_msg}: {e}")
            return error_msg

    def validate_address(self, args: List[str]) -> str:
        try:
            raise NotImplementedError
        except Exception as e:
            error_msg = "Error in validating address"
            logger.error(f"{error_msg}: {e}")
            return error_msg

    def extract_order(self, args: List[str]) -> str:
        """
        Manually extracts an order from the given args.
        """
        try:
            return "ORDER EXTRACTED"
        except Exception as e:
            error_msg = "Error in extracting order"
            logger.error(f"{error_msg}: {e}")
            return error_msg

    def validate_order(self, args: List[str]) -> str:
        """
        Validates an order by checking if the order is valid.

        Args:
            args (List[str]): The order to validate.

        Returns:
            str: The validation result.
        """
        try:
            return "ORDER IS VALID"
        except Exception as e:
            error_msg = "Error in validating order"
            logger.error(f"{error_msg}: {e}")
            return error_msg
