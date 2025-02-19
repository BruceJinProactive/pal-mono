import functools
import os
import re
import time
import traceback
import uuid

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import retrieval, task, tool
from llama_index.core import Settings, VectorStoreIndex
from llama_index.core.response_synthesizers import (
    ResponseMode,
    get_response_synthesizer,
)
from llama_index.core.vector_stores.types import ExactMatchFilter, MetadataFilters
from llama_index.embeddings.cohere import CohereEmbedding
from llama_index.llms.groq import Groq as GroqLLM
from llama_index.vector_stores.pinecone import PineconeVectorStore
from pinecone import Pinecone

from agent.legacy.storage import get_storage
from tools.adora_tool.classes import (
    AdoraAccessToken,
    CustomerInfo,
    DeliveryAddress,
    Order,
)
from utils.log import logger
from utils.secret import get_client_secret_with_fallback

from . import _apis, _utils

ADORA_PAYMENT_URL = "https://pizzamyheart.adorapos.net/OnlineOrdering/OrderHubPayment/?storeKey={store_id}&orderId={order_id}"


class AdoraTool(Toolkit):
    def __init__(
        self,
        store_id: str,
        agent_id: uuid.UUID,
        account_id: uuid.UUID,
        account_name: str,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        namespace: str,
    ):
        super().__init__(name="adora_tool")

        # Register tools
        self.register(self.check_online_ordering_status)
        self.register(self.get_store_info)
        self.register(self.checkout_order)

        self.store_id = store_id
        self.agent_id = agent_id
        self.account_id = account_id
        self.account_name = account_name
        self.user_id = user_id
        self.session_id = session_id
        self.namespace = namespace

        # TODO: This code is bad >:( Refactor once it works. (ToT)
        # We can fix this with
        pc = Pinecone(os.getenv("PINECONE_API_KEY"))
        pinecone_index = pc.Index("agents")

        vector_store = PineconeVectorStore(
            pinecone_index=pinecone_index, namespace=self.namespace
        )

        Settings.embed_model = CohereEmbedding(
            api_key=os.getenv("COHERE_API_KEY"),
            model_name="embed-english-v3.0",  # current v3 models support multimodal embeddings
        )

        # set groq llm
        llm = GroqLLM(model="llama-3.3-70b-versatile")
        Settings.llm = llm

        index = VectorStoreIndex.from_vector_store(
            vector_store=vector_store,
            embed_model=Settings.embed_model,
        )
        response_synthesizer = get_response_synthesizer(
            response_mode=ResponseMode.NO_TEXT,
        )

        self.query_engine = index.as_query_engine(
            similarity_top_k=10,
            similarity_cutoff=0.3,
            response_synthesizer=response_synthesizer,
            # Use the menu documents with ids for extraction
            filters=MetadataFilters(
                filters=[ExactMatchFilter(key="include_ids", value="True")]
            ),
        )

    @functools.cached_property
    def _adora_bearer_token(self) -> AdoraAccessToken | None:
        with LLMObs.task(name="get_adora_bearer_token"):
            api_key = get_client_secret_with_fallback("PIZZAMYHEART_ADORA_API_KEY")
            api_secret = get_client_secret_with_fallback(
                "PIZZAMYHEART_ADORA_API_SECRET"
            )
            bearer_token = _apis.get_adora_pos_auth_token(api_key, api_secret)
            return bearer_token

    @tool
    def check_online_ordering_status(self) -> str:
        """
        Check the online ordering status of the store.

        Returns:
            str: The online ordering status of the store.
        """
        # For test store, we always return "active" status
        if self.store_id == "9WHCV":
            return "The store is open for online ordering."

        try:
            if not self._adora_bearer_token:
                return "Failed to authenticate ordering tool. Please reach out to our support team at help@proactiveailab.com for assistance."

            status = _apis.get_online_ordering_status(
                self._adora_bearer_token, self.store_id
            )

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

    @task
    def _validate_address(self, canonical_address: DeliveryAddress) -> tuple[bool, str]:
        # Use the address to get the latitude and longitude of the address
        lat_lon_was_added, message = _utils.add_lat_long_to_address(canonical_address)  # type: ignore

        if lat_lon_was_added:
            assert isinstance(canonical_address, DeliveryAddress)
            lat, long = canonical_address.lat, canonical_address.lng
            logger.info(f"Latitude and longitude extracted: {lat}, {long}")
        else:
            return False, message

        # Use the latitude and longitude to get Adora API call (old Jimmy)
        if not self._adora_bearer_token:
            return (
                False,
                "Failed to authenticate ordering tool. Please reach out to our support team at help@proactiveailab.com for assistance.",
            )

        validated_address_success, validated_address = _apis.validate_address(
            self._adora_bearer_token, self.store_id, lat, long
        )
        logger.info(f"Validated address: {validated_address}")

        if not validated_address_success:
            return False, "Address is not in the delivery zone."
        else:
            return True, "Address is validated and is in the delivery zone."

    @task
    def _get_content(self, text: str) -> str:
        match = re.search(r"<content>\s*(.*?)\s*</content>", text)
        return match.group(1) if match else ""

    @retrieval
    def _get_chat_history(self, latest_user_message: str) -> str:
        # TODO: Hacky way to get FULL chat history. Latest user message is not in storage.

        try:
            try:
                # # TODO: Defer import to avoid circular import
                # from services.admin_service import (
                #     get_messages_by_conversation_id,
                # )
                chat_history = ""
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

                    if latest_user_message:
                        chat_history += f"**[User]**\n{latest_user_message}\n\n"
                        return chat_history

                    return "Agent session not found"

                messages = agent_session.memory["runs"]  # type: ignore

                for message in messages:
                    role = message["message"]["role"]
                    if role == "user":
                        user_content = self._get_content(message["message"]["content"])  # type: ignore
                        chat_history += f"**[User]**\n{user_content}\n\n"
                        chat_history += (
                            f"**[Assistant]**\n{message['response']['content']}\n\n"
                        )
                    else:
                        logger.info(
                            f"Skipping appending message to chat history:\n{message}"
                        )

                chat_history += f"**[User]**\n{latest_user_message}\n\n"

                LLMObs.annotate(output_data=chat_history)

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

    @retrieval
    def _get_relevant_docs(self, chat_history: str) -> str:
        response = self.query_engine.query(chat_history)

        context = ""
        output_data = []
        for node in response.source_nodes:
            context += f"{node.text}\n\n"
            output_data.append({"id": node.id_, "text": node.text})

        LLMObs.annotate(input_data=chat_history, output_data=output_data)

        return context

    @task(name="_fulfill_order [via Adora API]")
    def _fulfill_order(self, order: Order, bearer_token: AdoraAccessToken) -> str:
        LLMObs.annotate(input_data=order)

        json_payload = order.model_dump_json(by_alias=True)
        validated_order = _apis.validate_order(
            bearer_token=bearer_token, json_payload=json_payload
        )

        logger.info(f"[AdoraTool.checkout_order] Validated order: {validated_order}")

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

        Subtotal: {validated_order.subTotal}
        Sales Tax: {validated_order.taxAmount}
        Order Total: {validated_order.total}
        """

    @tool
    def checkout_order(self, latest_user_message: str) -> str:
        """
        Validates an order for checkout by extracting structured ordering data from chat history. This function should be invoked when the user asks to checkout, pay, place the order, etc.

        Args:
            last_user_message (str): The latest user message in the chat history.

        Returns:
            str: The checkout order details including the payment URL.
        """

        chat_history: str = self._get_chat_history(latest_user_message)  # type: ignore

        context = self._get_relevant_docs(chat_history)  # type: ignore

        # Extract structured data from natural language
        try:
            # current version of the datadog llmobs does not support pyright
            order = _utils.llm_call(
                system_prompt=_utils.EXTRACTOR_SYSTEM_PROMPT,
                prompt=_utils.EXTRACTOR_USER_PROMPT.format(
                    context=context, chat_history=chat_history
                ),
                response_format=Order,
            )

            if not isinstance(order, Order):
                logger.error(
                    "[AdoraTool.checkout_order] Failed to extract structured data. Most likely validation schema was not fulfilled."
                )
                return "Failed to extract structured data. Please try again."

            # Validate the address if the order is for delivery
            if str(order.order_type) == "Delivery":
                start_time = time.time()
                validate_order_success, validate_order_message = self._validate_address(
                    order.delivery_address  # type: ignore
                )
                end_time = time.time()
                logger.info(
                    f"Time taken to validate address: {end_time - start_time} seconds"
                )

                if not validate_order_success:
                    return validate_order_message

            logger.info(f"Extracted structured data: {order}")
            logger.info(f"Extraced structured data type: {type(order)}")

            api_key = get_client_secret_with_fallback("PIZZAMYHEART_ADORA_API_KEY")
            api_secret = get_client_secret_with_fallback(
                "PIZZAMYHEART_ADORA_API_SECRET"
            )
            bearer_token = _apis.get_adora_pos_auth_token(api_key, api_secret)
            if not bearer_token:
                return "Failed to authenticate ordering tool. Please reach out to our support team at help@proactiveailab.com for assistance."

            # Override store id
            order.store_id = self.store_id

            # Manually set customer info for now
            order.customer = CustomerInfo(
                first_name="Jimmy",
                last_name="ProactiveAILab (via Jimmy)",
                phone_number="(555)555-5555",
                email="jimmythesurfer@proactiveailab.com",
            )

            # If order comment is None, set it to an empty string
            order.order_comment = "" if not order.order_comment else order.order_comment

            # Move order_items to the items field which fulfills the Adora API requirements
            items = []
            for order_item in order.order_items:
                items.append({"group": [order_item]})
            order.items = items

            return self._fulfill_order(order, bearer_token)  # type: ignore

        except Exception as e:
            logger.error(f"Error in extracting structured data: {e}")
            logger.error(traceback.format_exc())
            return "Error in extracting structured data."
