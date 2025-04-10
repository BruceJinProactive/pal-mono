import asyncio
import functools
import json
import os
import traceback
from datetime import datetime

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import retrieval, task, tool
from mixpanel import Mixpanel

from agent.config import ClientConfig
from agent.memory import update_memory
from agent.tool import ToolMetadata
from agent.tool.internal.query_messages_tool import QueryMessagesTool
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

ADORA_QA_STORE = "UQ5ZT"


class AdoraTool(Toolkit):
    def __init__(
        self,
        store_id: str,
        namespace: str,
        tool_metadata: ToolMetadata,
        client_config: ClientConfig,
    ):
        super().__init__(name="adora_tool")

        # Configs
        self.store_id = store_id
        self.namespace = namespace
        self.tool_metadata = tool_metadata
        self.discounts = []  # { coupon_id, discount_code }

        if self.store_id == ADORA_QA_STORE:  # QA store
            self.qa_store = True
        else:
            self.qa_store = False
            self.discounts = client_config.data.get("discounts", [])

        ### Cache adora token and store info ###
        self.cached_store_info: str | None = None

        loop = asyncio.get_running_loop()
        loop.create_task(asyncio.to_thread(lambda: self._adora_bearer_token))

        # Register tools
        # self.register(self.greeting) # TODO: let's unregister this
        self.register(self.check_online_ordering_status)
        self.register(self.get_store_info)
        self.register(self.checkout_order)
        self.register(self.check_address)

        self.query_engine = _query_engine.create_query_engine(self.namespace)
        self.query_messages_tool = QueryMessagesTool(self.tool_metadata)

        # Initialize Mixpanel
        MIXPANEL_PROJECT_TOKEN = os.getenv("MIXPANEL_PROJECT_TOKEN")
        self.mp = None
        if MIXPANEL_PROJECT_TOKEN:
            self.mp = Mixpanel(MIXPANEL_PROJECT_TOKEN)

    @functools.cached_property
    def _adora_bearer_token(self) -> AdoraAccessToken | None:
        with LLMObs.task(name="get_adora_bearer_token"):
            if self.qa_store:
                api_key = get_client_secret_with_fallback("ADORA_API_KEY")
                api_secret = get_client_secret_with_fallback("ADORA_API_SECRET")
            else:
                api_key = get_client_secret_with_fallback("PIZZAMYHEART_ADORA_API_KEY")
                api_secret = get_client_secret_with_fallback(
                    "PIZZAMYHEART_ADORA_API_SECRET"
                )
            bearer_token = _apis.get_adora_pos_auth_token(
                api_key, api_secret, qa_store=self.qa_store
            )
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
                return (
                    "Failed to authenticate ordering tool. Please reach out to our "
                    "support team at help@palona.ai for assistance."
                )

            customer_info = _apis.get_customer_info(
                self._adora_bearer_token,
                self.store_id,
                phone_number,
                qa_store=self.qa_store,
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
                return (
                    "Failed to authenticate ordering tool. Please reach out to our "
                    "support team at help@palona.ai for assistance."
                )

            status = _apis.get_online_ordering_status(
                self._adora_bearer_token, self.store_id, qa_store=self.qa_store
            )

            if not status:
                raise ValueError(f"Returned invalid online store status: {status}")

            return status

        except Exception as e:
            logger.error(
                "[AdoraTool.check_online_ordering_status] "
                f"Error in checking online ordering status: {e}"
            )
            return "Failed to check the online ordering status, please try again."

    @tool
    def get_store_info(self, date: str) -> str:
        """
        Retrieves store details for the current date, including estimated wait times,
        business hours, and accepted payment methods.

        Args:
            date (str): The current date in yyyy-MM-dd format.

        Returns:
            str: Store details including:
                - Store name, address, and phone number.
                - Estimated wait times for delivery, dine-in, and takeout.
                - Business hours for delivery and pickup.
                - Accepted payment methods for dine-in, takeout, and delivery.
        """
        try:
            if not _utils.is_valid_date(date):
                return f"The date {date} is invalid."

            # Enforce that only current date is allowed
            current_date = datetime.now().strftime("%Y-%m-%d")
            if date != current_date:
                return (
                    f"This tool can only be used for the current date ({current_date})."
                )

            # If store info is already cached return it
            if self.cached_store_info:
                return self.cached_store_info

            if not self._adora_bearer_token:
                return (
                    "Failed to authenticate ordering tool. "
                    "Please reach out to our support team at help@palona.ai "
                    "for assistance."
                )

            store_info = _apis.get_store_info(
                self._adora_bearer_token, self.store_id, date, qa_store=self.qa_store
            )

            if not store_info:
                raise ValueError(f"Returned invalid wait time: {store_info}")

            # Cache store info
            self.cached_store_info = store_info
            return store_info

        except Exception as e:
            logger.error(f"[AdoraTool.store_info] Error getting store info: {e}")
            return "Failed to get the wait time, please try again."

    @tool
    def check_address(self, address: str) -> str:
        """
        This tool can be used to validate whether or not an address is within a
        delivery zone. Call this tool whenever you need to confirm if a certain
        delivery address can be delivered to.

        Args:
            address (str): The delivery address to check.

        Returns:
            str: If the address is valid and within the delivery zone.
        """
        if not address:
            return "Could you provide your address?"

        delivery_address = _llm.llm_call(
            system_prompt="Extract the address into the given output format.",
            prompt=address,
            response_format=DeliveryAddress,
            reasoning=False,
        )

        if not isinstance(delivery_address, DeliveryAddress):
            return (
                "Failed to identify address. "
                "Please try again by providing the full address."
            )

        validate_order_success, validate_order_message = self._validate_address(
            delivery_address  # type: ignore
        )

        logger.info(
            f"Validated order: {validate_order_success}\n"
            f"Validate order message: {validate_order_message}"
        )

        return validate_order_message

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
                (
                    "Failed to authenticate ordering tool. "
                    "Please reach out to our support team at help@palona.ai "
                    "for assistance."
                ),
            )

        validated_address_success, validated_address = _apis.validate_address(
            self._adora_bearer_token, self.store_id, lat, long, qa_store=self.qa_store
        )
        logger.info(f"Validated address: {validated_address}")

        if not validated_address_success:
            return False, "Address is not in the delivery zone."
        else:
            return True, "Address is validated and is in the delivery zone."

    @retrieval
    async def _get_relevant_docs(self, chat_history: str) -> str:
        # Decompose chat history into multiple sub-queries
        sub_queries = _llm.llm_call(
            system_prompt=_llm.RETRIEVE_ORDER_ITEMS_SYSTEM_PROMPT,
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
        payload = order.model_dump_json(by_alias=True)

        LLMObs.annotate(input_data=order, metadata={"payload": payload})

        # Guaranteed phone number since we validated it in the order
        json_payload = json.loads(payload)
        phone_number = json_payload["customer"]["phone"]
        if not phone_number or not _utils.is_valid_phone_number(phone_number):
            return (
                f"{phone_number} is not a valid phone number. "
                "Please provide a valid phone number in the format XXX-XXX-XXXX."
            )

        if self.qa_store:  # Do not apply discount for QA store
            json_payload["coupons"] = []
            payload = json.dumps(json_payload)

        validated_order = _apis.validate_order(
            bearer_token=bearer_token, payload=payload, qa_store=self.qa_store
        )

        logger.info(f"[AdoraTool.checkout_order] Validated order: {validated_order}")

        if not validated_order or not validated_order.key:
            return "Failed to validate order. Please try again."

        text_payment_url = validated_order.paymentUrl

        if self.mp:
            event_properties = {
                "action_name": AdoraTool.checkout_order.__name__,
                "account_name": self.tool_metadata.account_name,
                "conversation_id": str(self.tool_metadata.session_id),
                "order_key": validated_order.key,
                "order_payment_url": text_payment_url,
                "order_total": (
                    float(validated_order.total)
                    if validated_order.total is not None
                    else 0.0
                ),
            }
            self.mp.track(
                str(self.tool_metadata.user_id),
                AnalyticsEvent.CRITICAL_ACTION,
                event_properties,
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

        output += (
            "\n\nYou MUST include the EXACT payment url in your response:\n"
            f"{text_payment_url}"
        )

        LLMObs.annotate(output_data=output)

        return output

    @tool
    def checkout_order(self, latest_user_message: str) -> str:
        """
        Validates an order for checkout by extracting structured ordering data from chat
        history. This function absolutely must be invoked when the user asks to checkout,
        pay, place the order, etc.

        Args:
            latest_user_message (str): The latest user message in the chat history.

        Returns:
            str: The checkout order details including the payment URL.
        """
        try:
            chat_history: str = self.query_messages_tool.query_messages(latest_user_message)  # type: ignore

            context = asyncio.run(self._get_relevant_docs(chat_history))  # type: ignore

            final_extractor_system_prompt = _llm.EXTRACTOR_SYSTEM_PROMPT
            if self.discounts:
                final_extractor_system_prompt += (
                    "\n\n"
                    + _llm.DISCOUNT_SYSTEM_PROMPT.format(discounts=self.discounts)
                )

            order = _llm.llm_call(
                system_prompt=final_extractor_system_prompt,
                prompt=_llm.EXTRACTOR_USER_PROMPT.format(
                    context=context, chat_history=chat_history
                ),
                response_format=Order,
                reasoning=False,
            )

            if not isinstance(order, Order):
                logger.error(
                    f"`order` object in type {type(order)} but expected type Order.\n"
                    f"`order` object: {order}"
                )
                if isinstance(order, str):
                    order = Order.model_validate(json.loads(order))
                else:
                    return "Failed to extract structured data. Please try again."

            if not order.order_type:
                logger.error("No order type specified.")
                return "Sorry, do you want that for Takeout or Delivery?"

            try:
                # Adora requires a string 'Delivery' or 'TakeOut' as the order type
                order.order_type = _utils.validate_order_type(order.order_type)
            except Exception as e:
                logger.error(f"Could not validate order type: {e}")
                return "Sorry, do you want that for Takeout or Delivery?"

            # Validate the address if the order is for delivery
            if order.order_type == AdoraOrderType.DELIVERY:
                validate_order_success, validate_order_message = self._validate_address(
                    order.delivery_address  # type: ignore
                )

                if not validate_order_success:
                    return validate_order_message

            logger.debug(f"Extracted structured data: {order}")
            logger.debug(f"Extracted structured data type: {type(order)}")
            if not self._adora_bearer_token:
                return (
                    "Failed to authenticate ordering tool. "
                    "Please reach out to our support team at help@palona.ai "
                    "for assistance."
                )

            # Override store id
            order.store_id = self.store_id

            ### Validate and check fields ###
            if not order.customer:
                logger.error("Customer info is missing.")
                return "We'll need your first name and phone number to place the order."
            elif not order.customer.first_name:
                logger.error("Customer first name is missing.")
                return "We'll need your first name."
            elif not order.customer.phone_number:
                logger.error("Customer phone number is missing.")
                return "We'll need your phone number."

            order.customer.last_name = (
                "(via Jimmy)"
                if not order.customer.last_name
                else f"{order.customer.last_name} (via Jimmy)"
            )

            # Set email to default if empty or if it is not valid
            email = order.customer.email
            if not email or not _utils.is_valid_email(email):
                order.customer.email = "jimmythesurfer@palona.ai"

            # If order comment is None, set it to an empty string
            order.order_comment = "" if not order.order_comment else order.order_comment

            return self._fulfill_order(order, self._adora_bearer_token)  # type: ignore

        except Exception as e:
            logger.error(f"Error in extracting structured data: {e}")
            logger.error(traceback.format_exc())
            return "Please try again."
