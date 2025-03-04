import asyncio
import functools
import os
import time
import traceback
import uuid

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import retrieval, task, tool
from mixpanel import Mixpanel

from agent.legacy.storage import get_storage
from agent.memory import update_memory
from api.schemas.admin.analytics import Event as AnalyticsEvent
from tools.adora_tool.classes import (
    AdoraAccessToken,
    AdoraOrderType,
    DeliveryAddress,
    Order,
    SubQueries,
)
from utils.log import logger
from utils.secret import get_client_secret_with_fallback

from . import _apis, _llm, _query_engine, _utils

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

        # Evaluate and cache the value of the bearer token
        loop = asyncio.get_running_loop()
        loop.create_task(asyncio.to_thread(lambda: self._adora_bearer_token))

        # Register tools
        self.register(self.greeting)
        self.register(self.check_online_ordering_status)
        self.register(self.get_wait_time)
        self.register(self.checkout_order)

        self.store_id = store_id
        self.agent_id = agent_id
        self.account_id = account_id
        self.account_name = account_name
        self.user_id = user_id
        self.session_id = session_id
        self.namespace = namespace

        self.query_engine = _query_engine.create_query_engine(self.namespace)

        # Initialize Mixpanel
        MIXPANEL_PROJECT_TOKEN = os.getenv("MIXPANEL_PROJECT_TOKEN")
        self.mp = None
        if MIXPANEL_PROJECT_TOKEN:
            self.mp = Mixpanel(MIXPANEL_PROJECT_TOKEN)

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
    def greeting(self, phone_number: str) -> str:
        """
        Greet the customer and check if their info exists in the Adora database.
        If so, retrieve their info and use that to greet them.

        Args:
            phone_number (str): The phone number.

        Returns:
            str: Greeting to the customer.
        """
        try:
            phone_number = _utils.format_phone_number(phone_number)
            if not phone_number:
                raise ValueError("Invalid phone number format.")

            if not self._adora_bearer_token:
                return "Failed to authenticate ordering tool. Please reach out to our support team at help@proactiveailab.com for assistance."

            customer_info = _apis.get_customer_info(
                self._adora_bearer_token, self.store_id, phone_number
            )

            # If customer does not exist or something else happened
            if customer_info is None:
                raise ValueError(f"Returned invalid customer info: {customer_info}")

            # If the customer info exists in PMH
            if customer_info:
                # TODO: Maybe not the best way to update memory?
                asyncio.run(
                    update_memory(
                        user_id=str(self.user_id),  # type: ignore
                        content=customer_info,  # type: ignore
                    )
                )

            return customer_info

        except Exception as e:
            logger.error(f"[AdoraTool.greeting] Error in greeting customer: {e}")
            return ""

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
                raise ValueError(f"Returned invalid online store status: {status}")

            return status

        except Exception as e:
            logger.error(
                f"[AdoraTool.check_online_ordering_status] Error in checking online ordering status: {e}"
            )
            return "Failed to check the online ordering status, please try again."

    @tool
    def get_wait_time(self, date: str) -> str:
        """
        This tool can be used to help identify the wait time for a given date.

        Args:
            date (str): The target business date in yyyy-MM-dd format.

        Returns:
            str: Get details about estimated wait times for delivery, dine-in, and takeout.
        """
        try:
            if not _utils.is_valid_date(date):
                return f"The date {date} is invalid."

            if not self._adora_bearer_token:
                return "Failed to authenticate ordering tool. Please reach out to our support team at help@proactiveailab.com for assistance."

            store_info = _apis.get_wait_time(
                self._adora_bearer_token, self.store_id, date
            )

            if not store_info:
                raise ValueError(f"Returned invalid wait time: {store_info}")

            return store_info
        except Exception as e:
            logger.error(f"[AdoraTool.store_info] Error getting store info: {e}")
            return "Failed to get the wait time, please try again."

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
                        user_content = _utils.get_content(message["message"]["content"])
                        chat_history += f"**[User]**\n{user_content}\n\n"
                        chat_history += (
                            f"**[Assistant]**\n{message['response']['content']}\n\n"
                        )
                    else:
                        logger.info(
                            f"Skipping appending message to chat history:\n{message}"
                        )

                chat_history += f"**[User]**\n{latest_user_message}"

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
    async def _get_relevant_docs(self, chat_history: str) -> str:
        # Decompose chat history into multiple sub-queries
        sub_queries = _llm.llm_call(
            system_prompt="Identify all the order items of the user's final cart in the chat history.",
            prompt=chat_history,
            response_format=SubQueries,
            reasoning=False,
        )

        if not isinstance(sub_queries, SubQueries):
            return "Failed to identify the items the user ordered in the conversation."

        logger.info(f"Sub-queries identified: {sub_queries.queries}")

        # Perform knowledege retrieval on all sub-queries asynchronously
        tasks = [
            asyncio.create_task(self.query_engine.aquery(q))
            for q in sub_queries.queries
        ]
        results = await asyncio.gather(*tasks)

        context = ""
        output_data = []
        doc_id = 0
        for res in results:
            for node in res.source_nodes:
                if node.metadata:
                    context += (
                        f"<document index='{doc_id}'>\n"
                        "\t<document_content>\n"
                        f"\t\t{node.text}\n"
                        "\t</document_content>\n"
                        "</document>\n\n"
                    )
                    output_data.append({"id": node.id_, "text": node.text})
                    doc_id += 1

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
        if self.mp:
            event_properties = {
                "action_name": AdoraTool.checkout_order.__name__,
                "account_name": self.account_name,
                "conversation_id": str(self.session_id),
                "order_id": str(saved_order.orderID),
                "order_total": (
                    float(validated_order.total)
                    if validated_order.total is not None
                    else 0.0
                ),
            }
            self.mp.track(
                str(self.user_id), AnalyticsEvent.CRITICAL_ACTION, event_properties
            )

        output = (
            f"Your order is pending!\n"
            "Please head to the payment url to finalize your order!\n"
            f"{text_payment_url}\n\n"
            "Order Summary:\n"
            f"{order.order_items}\n\n"
            f"Subtotal: {validated_order.subTotal}\n"
            f"Sales Tax: {validated_order.taxAmount}\n"
        )

        if (
            order.order_type == AdoraOrderType.DELIVERY
            and validated_order.deliveryCharge
        ):
            output += f"Delivery Fee: {validated_order.deliveryCharge}\n"

        if validated_order.discount and validated_order.discount > 0.0:
            output += f"Discount: {validated_order.discount}\n"

        output += f"Order Total: {validated_order.total}\n"
        return output

    @tool
    def checkout_order(self, latest_user_message: str) -> str:
        """
        Validates an order for checkout by extracting structured ordering data from chat history. This function absolutely must be invoked when the user asks to checkout, pay, place the order, etc.

        Args:
            last_user_message (str): The latest user message in the chat history.

        Returns:
            str: The checkout order details including the payment URL.
        """
        try:
            chat_history: str = self._get_chat_history(latest_user_message)  # type: ignore

            context = asyncio.run(self._get_relevant_docs(chat_history))  # type: ignore

            order = _llm.llm_call(
                system_prompt=_llm.EXTRACTOR_SYSTEM_PROMPT,
                prompt=_llm.EXTRACTOR_USER_PROMPT.format(
                    context=context, chat_history=chat_history
                ),
                response_format=Order,
                reasoning=False,
            )

            if not isinstance(order, Order):
                raise ValueError("Failed to extract structured data. Please try again.")
            if not order.order_type:
                logger.error("No order type specified.")
                return "Please specify the order type Takeout or Delivery."

            try:
                # Adora requires a string 'Delivery' or 'TakeOut' as the order type
                order.order_type = _utils.validate_order_type(order.order_type)
            except Exception as e:
                logger.error(f"Could not value order type: {e}")
                return "Please specify the order type as 'Takeout' or 'Delivery'."

            # Validate the address if the order is for delivery
            if order.order_type == AdoraOrderType.DELIVERY:
                validate_order_success, validate_order_message = self._validate_address(
                    order.delivery_address  # type: ignore
                )

                if not validate_order_success:
                    return validate_order_message

            logger.info(f"Extracted structured data: {order}")
            logger.info(f"Extraced structured data type: {type(order)}")

            if not self._adora_bearer_token:
                return "Failed to authenticate ordering tool. Please reach out to our support team at help@proactiveailab.com for assistance."

            # Override store id
            order.store_id = self.store_id

            if not order.customer:
                logger.error("Customer info is missing.")
                return "Customer info is missing."
            elif not order.customer.first_name:
                logger.error("Customer first name is missing.")
                return "Customer first name is missing."
            elif not order.customer.phone_number:
                logger.error("Customer phone number is missing.")
                return "Customer phone number is missing."

            order.customer.last_name = (
                "(via Jimmy)"
                if not order.customer.last_name
                else f"{order.customer.last_name} (via Jimmy)"
            )

            # Set email to default if empty or if it is not valid
            email = order.customer.email
            if not email or not _utils.is_valid_email(email):
                order.customer.email = "jimmythesurfer@proactiveailab.com"

            # TODO: Hardcode discount
            order.coupons = [{"coupon_id": 134}]

            # If order comment is None, set it to an empty string
            order.order_comment = "" if not order.order_comment else order.order_comment

            return self._fulfill_order(order, self._adora_bearer_token)  # type: ignore

        except Exception as e:
            logger.error(f"Error in extracting structured data: {e}")
            logger.error(traceback.format_exc())
            return "Error in extracting structured data."
