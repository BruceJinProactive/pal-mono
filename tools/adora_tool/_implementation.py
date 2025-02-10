import os
import re
import time
import traceback
import uuid
from typing import List

import instructor
from ddtrace.llmobs.decorators import tool
from llama_index.core import Settings, VectorStoreIndex
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.pinecone import PineconeVectorStore
from openai import OpenAI
from phi.tools.toolkit import Toolkit
from phi.utils.log import logger
from pinecone import Pinecone

from agent.legacy.storage import get_storage
from tools.adora_tool.classes import Order
from utils.secret import get_client_secret_with_fallback

from . import _apis

ADORA_PAYMENT_URL = "https://pizzamyheart.adorapos.net/OnlineOrdering/OrderHubPayment/?storeKey={store_id}&orderId={order_id}"


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
        self.register(self.checkout_order)

        self.store_id = "9WHCV"

        self.account_name = account_name
        self.account_id = account_id
        self.agent_id = agent_id
        self.user_id = user_id
        self.session_id = session_id

    @tool
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

    @tool
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

    @tool
    def validate_address(self, args: List[str]) -> str:
        try:
            raise NotImplementedError
        except Exception as e:
            logger.error(f"Error in validating address: {e}")
            return "Error in validating address."

    def _get_content(self, text: str) -> str:
        match = re.search(r"<content>\s*(.*?)\s*</content>", text)
        return match.group(1) if match else ""

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
                        user_content = self._get_content(message["message"]["content"])
                        chat_history += f"**[User]**\n{user_content}\n\n"
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

    @tool
    def checkout_order(self) -> str:
        """
        Validates an order for checkout by extracting structured ordering data from chat history. This function should be invoked when the user asks to checkout, pay, place the order, etc.

        Returns:
            str: The checkout order details including the payment URL.
        """
        chat_history = self._get_chat_history()

        logger.info(f">>> Chat history:\n{chat_history}")

        # Patch the OpenAI client
        client = instructor.from_openai(OpenAI())

        # Extract structured data from natural language
        try:
            order: Order = client.chat.completions.create(
                model="o1",
                response_model=Order,
                messages=[
                    {
                        "role": "system",
                        "content": f"""You are a precise data extractor. Your task is to extract order information ONLY from the provided chat history.

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
            logger.info(f"Extracted structured data: {order}")

            # TODO: This code is bad >:( Refactor once it works. (ToT)
            pc = Pinecone(os.getenv("PINECONE_API_KEY"))
            pinecone_index = pc.Index("agents")

            vector_store = PineconeVectorStore(
                pinecone_index=pinecone_index, namespace="pizzamyheart-v3"
            )

            Settings.embed_model = OpenAIEmbedding(
                model="text-embedding-3-large",
                dimensions=1024,
            )

            index = VectorStoreIndex.from_vector_store(
                vector_store=vector_store,
                embed_model=Settings.embed_model,
            )
            query_engine = index.as_query_engine()

            def extract_id(response: str):
                matches: list[str] = re.findall(r"\d+", response)
                return int(matches[0]) if matches else -1

            for i, item in enumerate(order.order_items):
                for j, modifier in enumerate(item.modifiers):
                    prompt = f"What is the id of `{modifier.modifier_name}`"
                    response = query_engine.query(prompt)
                    id = extract_id(response.response)
                    order.order_items[i].modifiers[j].modifier_id = id

                prompt = f"What is the id of `{item.item_name}`"
                response = query_engine.query(prompt)
                id = extract_id(response.response)
                order.order_items[i].item_id = id

            logger.info(f"New extracted structured data: {order}")

            api_key = get_client_secret_with_fallback("PIZZAMYHEART_ADORA_API_KEY")
            api_secret = get_client_secret_with_fallback(
                "PIZZAMYHEART_ADORA_API_SECRET"
            )
            bearer_token = _apis.get_adora_pos_auth_token(api_key, api_secret)
            if not bearer_token:
                return "Failed to authenticate ordering tool. Please reach out to our support team at help@proactiveailab.com for assistance."

            order.store_id = self.store_id

            # Manually set customer info for now
            order.customer.first_name = "Jimmy"
            order.customer.last_name = "ProactiveAILab (via Jimmy)"
            order.customer.phone_number = "(555)555-5555"
            order.customer.email = "jimmythesurfer@proactiveailab.com"

            # Move order_items to the items field which fulfills the Adora API requirements
            order.items[0]["group"] = order.order_items

            json_payload = order.model_dump_json(by_alias=True)
            validated_order = _apis.validate_order(
                bearer_token=bearer_token, json_payload=json_payload
            )

            logger.info(
                f"[AdoraTool.checkout_order] Validated order: {validated_order}"
            )

            if not validated_order or not validated_order.key:
                return "Failed to validate order. Please try again."

            # save validated order in Adora system, get order ID
            logger.info("[AdoraTool.checkout_order] Saving validated order...")

            saved_order = _apis.save_validated_order(bearer_token, validated_order.key)

            if not saved_order or not saved_order.orderID:
                return "Failed to place order. Please try again."

            # delay 1 second to allow Adora to synchronize the order
            time.sleep(1)

            if saved_order:
                text_payment_url = ADORA_PAYMENT_URL.format(
                    store_id=self.store_id,
                    order_id=saved_order.orderID,
                )
            else:
                logger.debug(
                    f"[AdoraTool.checkout_order] Failed to place order. Saved order ID: {saved_order.orderID if saved_order else 'NO SAVED ORDER'}"
                )
                return "The service is busy. Please try again."

            return f"""Your order is pending!
            Please head to the payment url to finalize your order!
            {text_payment_url}
            
            Order Summary:
            {order.items}

            Total Price: {validated_order.total}
            """
        except Exception as e:
            logger.error(f"Error in extracting structured data: {e}")
            logger.error(traceback.format_exc())
            return "Error in extracting structured data."
