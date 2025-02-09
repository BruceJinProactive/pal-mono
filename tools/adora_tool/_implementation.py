import uuid
from typing import List

import instructor
from openai import OpenAI
from phi.tools.toolkit import Toolkit
from phi.utils.log import logger

from agent.legacy.storage import get_storage
from utils.secret import get_client_secret_with_fallback

from . import _apis
from .classes import Order


class AdoraTool(Toolkit):
    def __init__(
        self,
        account_name: str,
        account_id: uuid.UUID,
        agent_id: uuid.UUID,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
    ):
        super().__init__(name="adora_tool")

        # Register tools
        self.register(self.check_online_ordering_status)
        self.register(self.get_store_info)
        self.register(self.validate_address)
        self.register(self.validate_order)

        self.store_id = "9WHCV"

        self.account_name = account_name
        self.account_id = account_id
        self.agent_id = agent_id
        self.user_id = user_id
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
            logger.error(f"Error in checking online ordering status: {e}")
            return "Error in checking online ordering status."

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
            logger.error(f"Error getting store info: {e}")
            return "Error getting store info."

    def validate_address(self, args: List[str]) -> str:
        try:
            raise NotImplementedError
        except Exception as e:
            logger.error(f"Error in validating address: {e}")
            return "Error in validating address."

    def _get_chat_history(self) -> str:
        try:
            # db_session = db.get_db()

            # logger.info(db_session)
            # if not db_session:
            #     logger.error(
            #         "Failed to get database session for\n"
            #         f"Account Name: {self.account_name}\n"
            #         f"Account ID: {self.account_id}\n"
            #         f"Agent ID: {self.agent_id}\n"
            #         f"User ID: {self.user_id}\n"
            #         f"Session ID: {self.session_id}"
            #     )
            #     return "Failed to get database session."

            try:
                # # TODO: Defer import to avoid circular import
                # from services.admin_service import (
                #     get_messages_by_conversation_id,
                # )

                # messages = get_messages_by_conversation_id(
                #     db_session, self.user_id, self.session_id
                # )
                storage = get_storage(self.account_name)
                agent_session = storage.read(str(self.session_id), str(self.user_id))

                if not agent_session:
                    logger.error(
                        "Agent session not found for\n"
                        f"Account Name: {self.account_name}\n"
                        f"Account ID: {self.account_id}\n"
                        f"Agent ID: {self.agent_id}\n"
                        f"User ID: {self.user_id}\n"
                        f"Session ID: {self.session_id}"
                    )
                    return "Agent session not found"

                messages = agent_session.memory["runs"]  # type: ignore

                chat_history = ""

                for message in messages:
                    role = message["message"]["role"]
                    if role == "user":
                        chat_history += f"**[User]**\n{message['message']['content']}"
                        chat_history += (
                            f"**[Assistant]**\n{message['response']['content']}\n\n"
                        )
                    else:
                        logger.info(
                            f"Skipping appending message to chat history:\n{message}"
                        )

                return chat_history

            except ValueError:
                logger.error(
                    "Conversation history not found for\n"
                    f"Account ID: {self.account_id}\n"
                    f"Agent ID: {self.agent_id}\n"
                    f"User ID: {self.user_id}\n"
                    f"Session ID: {self.session_id}"
                )
                return "Conversation history not found."

        except Exception as e:
            error_msg = "Error in getting chat history"
            logger.error(f"{error_msg}: {e}")
            return error_msg

    def validate_order(self) -> str:
        """
        Validates an order for checkout by extracting structured ordering data from chat history.

        Returns:
            str: Whether or not the order was successfully validated.
        """
        import datetime

        s = datetime.datetime.now()
        chat_history = self._get_chat_history()
        e = datetime.datetime.now()
        logger.info(f">>> Time to get chat history: {(e - s).total_seconds()}s")
        logger.info(f">>> Chat history:\n{chat_history}")

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
                        "content": f"""
                        You are a precise data extractor. Your task is to extract order information ONLY from the provided chat history.

                        **IMPORTANT RULES:**
                        - Do NOT make assumptions or fabricate data
                        - Leave fields as None/null if the information is not explicitly mentioned
                        - Do not infer values from context
                        - Only extract information that is directly stated
                        - Maintain exact values as mentioned (don't modify numbers or text)
                        - For phone numbers, only extract if a complete number is provided
                        - For addresses, only extract if all required components are present

                        If unsure about any field, leave it empty rather than guessing.

                        ## Chat History:
                        {chat_history}
                        """,
                    }
                ],
            )
            logger.info(f"Extracted structured data: {res}")
            return res.model_dump_json()
        except Exception as e:
            logger.error(f"Error in extracting structured data: {e}")
            return "Error in extracting structured data."
