from typing import List

import instructor
from openai import OpenAI
from phi.tools.toolkit import Toolkit
from phi.utils.log import logger

from utils.secret import get_client_secret_with_fallback

from . import _apis
from .classes import Order


class AdoraTool(Toolkit):
    def __init__(self, session_id: str):
        super().__init__(name="adora_tool")

        # Register tools
        self.register(self.check_online_ordering_status)
        self.register(self.get_store_info)
        self.register(self.validate_address)
        self.register(self.validate_order)

        self.store_id = "9WHCV"
        self.session_id = session_id

    def check_online_ordering_status(self) -> str:
        """
        Check the online ordering status of the store.

        Returns:
            str: The online ordering status of the store.
        """
        try:
            api_key = get_client_secret_with_fallback("PIZZAMYHEART_ADORA_API_KEY")
            api_secret = get_client_secret_with_fallback(
                "PIZZAMYHEART_ADORA_API_SECRET"
            )
            bearer_token = _apis.get_adora_pos_auth_token(api_key, api_secret)
            if not bearer_token:
                return "Failed to authenticate ordering tool. Please reach out to our support team at help@proactiveailab.com for assistance."

            status = _apis.get_online_ordering_status(bearer_token, self.store_id)

            if not status:
                logger.error(
                    "[AdoraTool.check_online_ordering_status] Failed to get online ordering status."
                )
                return "Failed to check the online ordering status, please try again."

            return status

        except Exception as e:
            error_msg = "Error in checking online ordering status"
            logger.error(f"{error_msg}: {e}")
            return error_msg

    def get_store_info(self, store_id: str, date: str) -> str:
        """
        Get the store information by given store id and target business date.

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

        # Patch the OpenAI client
        client = instructor.from_openai(OpenAI())

        # Extract structured data from natural language
        try:
            res = client.chat.completions.create(
                model="o1",
                response_model=Order,
                messages=[
                    {
                        "role": "system",
                        "content": """
                        You are a precise data extractor. Your task is to extract order information ONLY from the provided chat history.
                        IMPORTANT RULES:
                        - Do NOT make assumptions or fabricate data
                        - Leave fields as None/null if the information is not explicitly mentioned
                        - Do not infer values from context
                        - Only extract information that is directly stated
                        - Maintain exact values as mentioned (don't modify numbers or text)
                        - For phone numbers, only extract if a complete number is provided
                        - For addresses, only extract if all required components are present

                        If unsure about any field, leave it empty rather than guessing.
                        """,
                    }
                    # TODO: Add messages from chat history
                ],
            )
            logger.info(f"Extracted structured data: {res}")
        except Exception as e:
            logger.error(f"Error in extracting structured data: {e}")

        try:
            return "ORDER IS VALID"
        except Exception as e:
            error_msg = "Error in validating order"
            logger.error(f"{error_msg}: {e}")
            return error_msg
