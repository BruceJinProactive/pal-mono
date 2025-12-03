import asyncio
import json
import textwrap
import time
import traceback
import urllib.parse
import uuid
from datetime import datetime
from functools import cached_property
from typing import Any, Optional
from zoneinfo import ZoneInfo

import polyline
from agno.tools.toolkit import Toolkit
from cryptography.fernet import Fernet
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import retrieval, task, tool
from pydantic import ValidationError
from shapely import Point, Polygon

from agent.tool import ToolMetadata
from agent.tool.internal.query_messages_tool import QueryMessagesTool
from tools.toast_tool._apis import (
    create_payment_intent,
    get_existing_order,
    get_menu_inventory,
    get_online_ordering_status,
    get_order_prices,
    get_ordering_schedule,
    get_store_info,
    submit_order,
)
from tools.toast_tool._prompt_constants import (
    DINING_OPTIONS_INSTRUCTION,
    EXTRACTOR_SYSTEM_PROMPT,
    EXTRACTOR_USER_PROMPT,
    RETRIEVE_ORDER_ITEMS_SYSTEM_PROMPT,
)
from tools.toast_tool._utils import (
    add_lat_long_to_address,
    get_toast_access_token_from_aws,
    is_within_service_periods,
    parse_service_periods,
    validate_item_modifier_quantity,
)
from tools.toast_tool.classes import (
    AppliedServiceCharge,
    DeliveryAddress,
    DiningBehavior,
    Modifier,
    Order,
    OrderInput,
    PaymentIntentRequest,
    PaymentIntentResponse,
    PaymentStatus,
    Price,
    SelectionType,
    SubQueries,
    ToastAccessToken,
)
from tools.utils.ordering._llm import llm_call
from tools.utils.ordering._query_engine import create_query_engine
from tools.utils.ordering._utils import (
    format_phone_number,
    is_valid_email,
    is_valid_phone_number,
)
from tools.utils.ordering.classes import OrderConstructionModel
from tools.utils.url_shortener import shorten_url
from utils.log import logger

# Agent identification suffix for customer names
VIA_AGENT_SUFFIX = "(via PalonaAI)"

# Fernet encryption key for payment iframe tokens (same as Olo for consistency)
HARD_CODED_PAYMENT_IFRAME_SECRET = "xK8dP2m_QrZ7vN4wL9cF3bJ6hT5yU1gS0aE8iO-pMxA="


class ToastTool(Toolkit):
    def __init__(
        self,
        store_id: str,
        namespace: str,
        tool_metadata: ToolMetadata,
        index_name: str | None = None,
        loyalty_enabled: bool = False,
        coupons_enabled: bool = False,
        default_coupon_id: str | None = None,
        token_api_endpoint: str | None = "ws-api.toasttab.com",
        general_api_endpoint: str | None = "ws-api.toasttab.com",
        # todo: refactor self.sandbox logic.
        sandbox: bool = False,
        hosted_payment_iframe_endpoint: str = "http://localhost:3000/checkout/toast",
        enable_hosted_checkout: bool = False,
        payment_iframe_token_ttl_seconds: int = 15 * 60,
        backdoor_tool_prompt: dict | None = None,
        order_construction_model: OrderConstructionModel = OrderConstructionModel.OPENAI,
        revenue_center_id: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(name="toast_tool")

        # Backward compatibility: handle old parameter name
        if "order_construction_model_name" in kwargs:
            order_construction_model = kwargs["order_construction_model_name"]
            logger.warning(
                "Parameter 'order_construction_model_name' is deprecated. Use 'order_construction_model' instead."
            )

        # Log instance creation with built-in id
        instance_id = id(self)
        logger.debug(f"ToastTool instance created: id={instance_id}")

        # Configs
        self.store_id = store_id
        self.namespace = namespace
        self.index_name = index_name
        self.tool_metadata = tool_metadata
        self.loyalty_enabled = loyalty_enabled
        self.coupons_enabled = coupons_enabled
        self.default_coupon_id = default_coupon_id
        self.token_api_endpoint = token_api_endpoint
        self.general_api_endpoint = general_api_endpoint
        self.sandbox = sandbox
        self._cached_store_info: str | None = None
        # Use sandbox iframe endpoint for hosted checkout
        self.hosted_payment_iframe_endpoint = hosted_payment_iframe_endpoint
        self.enable_hosted_checkout = enable_hosted_checkout
        self.payment_iframe_token_ttl_seconds = payment_iframe_token_ttl_seconds
        self.backdoor_tool_prompt = backdoor_tool_prompt or {}
        self.order_construction_model = order_construction_model
        self.revenue_center_id = revenue_center_id

        # Register tools
        if self.enable_hosted_checkout:
            self.register(self.checkout_order_with_payment_iframe)
        else:
            self.register(self.checkout_order)

        # Do not register get_menu_inventory_tool and get_ordering_schedule_tool for now
        self.register(self.get_ordering_schedule_tool)
        self.register(self.is_online_order_available)
        self.register(self.check_address)
        # TODO: Figure out how to check if an item is out of stock or has low quantity
        # self.register(self.get_menu_inventory_tool)

        # Retrieval tools
        self.query_messages_tool = QueryMessagesTool(self.tool_metadata)
        if self.index_name:
            self.query_engine = create_query_engine(
                namespace=self.namespace, index_name=self.index_name
            )
        else:
            self.query_engine = None

        # TODO: See if the following lines are needed
        # loop = asyncio.get_running_loop()
        # loop.create_task(asyncio.to_thread(lambda: self._toast_bearer_token))

    @cached_property
    def _payment_iframe_fernet(self) -> Fernet:
        """Fernet encryptor for payment iframe tokens."""
        try:
            return Fernet(HARD_CODED_PAYMENT_IFRAME_SECRET.encode("utf-8"))
        except ValueError as exc:
            raise ValueError(
                "HARD_CODED_PAYMENT_IFRAME_SECRET must be a URL-safe base64-encoded 32-byte key"
            ) from exc

    @property
    def _toast_bearer_token(self) -> ToastAccessToken | None:
        with LLMObs.task(name="get_toast_bearer_token"):
            if self.sandbox:
                return get_toast_access_token_from_aws(
                    self.token_api_endpoint,
                    token_name="TOAST_SANDBOX_ACCESS_TOKEN",
                    credential_name="TOAST_SANDBOX_CLIENT_CREDENTIALS",
                )
            return get_toast_access_token_from_aws(self.token_api_endpoint)

    @property
    def _toast_hosted_payment_checkout_bearer_token(self) -> ToastAccessToken | None:
        with LLMObs.task(name="get_toast_hosted_payment_checkout_bearer_token"):
            return get_toast_access_token_from_aws(
                self.token_api_endpoint,
                token_name="TOAST_PAYMENT_CHECKOUT_ACCESS_TOKEN",
                credential_name="TOAST_PAYMENT_CHECKOUT_CLIENT_CREDENTIALS",
            )

    @property
    def _toast_hosted_payment_iframe_bearer_token(self) -> ToastAccessToken | None:
        with LLMObs.task(name="get_toast_hosted_payment_iframe_bearer_token"):
            return get_toast_access_token_from_aws(
                self.token_api_endpoint,
                token_name="TOAST_PAYMENT_IFRAME_ACCESS_TOKEN",
                credential_name="TOAST_PAYMENT_IFRAME_CLIENT_CREDENTIALS",
            )

    def _get_delivery_area(self) -> str:
        """
        Retrieves the delivery area polyline string from store configuration.

        Returns:
            str: Either the polyline string or an error message
        """
        store_info_str = self.get_store_info()
        if store_info_str == "Failed to get the store information, please try again.":
            return store_info_str

        try:
            store_info = json.loads(store_info_str)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse store info JSON: {e}")
            return "Failed to process store information."

        polyline_str = (
            store_info.get("delivery", {}).get("area")
            if "delivery" in store_info
            else None
        )

        if not polyline_str:
            return "Delivery area information is not available."

        return polyline_str

    @task
    def _validate_address(
        self, canonical_address: DeliveryAddress | None
    ) -> tuple[bool, str]:
        """
        Validates if an address is within the delivery zone polygon.

        Args:
            canonical_address: The address to validate with lat/lng

        Returns:
            tuple[bool, str]: (is_valid, message)
        """
        # Validate input
        if not canonical_address:
            return (False, "Could you provide your complete address?")

        # Get store delivery area
        polyline_str = self._get_delivery_area()
        # Check if polyline_str is an error message
        if polyline_str in [
            "Failed to get the store information, please try again.",
            "Failed to process store information.",
            "Delivery area information is not available.",
        ]:
            return (False, polyline_str)

        # Decode and validate
        try:
            decoded = polyline.decode(polyline_str, geojson=True)
            polygon = Polygon([(lng, lat) for lng, lat in decoded])

            point = Point(canonical_address.lng, canonical_address.lat)

            if polygon.contains(point):
                return (True, "Address is within the delivery area.")
            else:
                return (False, "Address is outside the delivery area.")

        except Exception as e:
            logger.error(f"Error validating delivery zone: {e}")
            return (False, "Failed to validate delivery area.")

    @tool
    def check_address(self, address: str) -> str:
        """
        Validates if the given address is within the restaurant's delivery area.

        Args:
            address (str): The address to validate.

        Returns:
            str: A message indicating whether the address is within the delivery area.
        """
        # Step 1: Input validation
        if not address:
            return "Could you provide your address?"

        # Step 2: Extract address using LLM
        delivery_address = llm_call(
            system_prompt="Extract the address into the given output format.",
            prompt=address,
            response_format=DeliveryAddress,
            openai=False,
        )

        if not isinstance(delivery_address, DeliveryAddress):
            return (
                "Failed to identify address. "
                "Please try again by providing the full address."
            )

        # Step 3: Add lat/long to address (uses utility function)
        success, message, delivery_address = add_lat_long_to_address(delivery_address)
        if not success:
            return message

        # Step 4: Validate delivery zone (DELEGATED to helper method)
        validate_success, validate_message = self._validate_address(delivery_address)  # type: ignore

        return validate_message

    @tool
    def get_store_info_tool(self) -> str:
        """
        Retrieves detailed configuration information for a specific restaurant.

        Args:
            None

        Returns:
            str: A JSON-formatted string containing:
                - Basic restaurant information (e.g., name, timezone, GUID)
                - Location details such as address and phone number
                - Delivery and online ordering configuration
                - Operating hours and schedule data
                - Prep times and supported web URLs
        """

        return self.get_store_info()

    def get_store_info(self) -> str:
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

            store_info = get_store_info(
                self._toast_bearer_token,
                self.store_id,
                general_api_endpoint=self.general_api_endpoint,
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

        Args:
            None

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
                self._toast_bearer_token,
                self.store_id,
                general_api_endpoint=self.general_api_endpoint,
            ).model_dump_json()

            return status

        except Exception as e:
            logger.error(
                "[ToastTool.check_online_ordering_status] "
                f"Error in checking online ordering status: {e}"
            )
            return "Failed to check the online ordering status, please try again."

    @tool
    def is_online_order_available(self) -> str:
        """
        Check if the store is currently open for online ordering based on the service periods.
        """
        logger.debug(
            "[ToastTool.is_online_order_available] Checking if store is open for ordering ..."
        )
        is_open = self._is_online_order_available()

        if not is_open:
            return "Store is closed for ordering. You must let the user know."

        return "Store is open for ordering."

    def _is_online_order_available(
        self, dining_behavior: Optional[DiningBehavior] = DiningBehavior.TAKE_OUT
    ) -> bool:
        """
        Check if the store is currently open for online ordering based on the service periods.

        Args:
            dining_behavior: Optional dining behavior to check (TAKE_OUT, DELIVERY, etc.)
                           If None, checks all service periods. Currently only supports TAKE_OUT.

        Returns:
            bool: True if store is open for ordering, False otherwise
        """
        try:
            if not self._toast_bearer_token:
                logger.error(
                    "[ToastTool._is_online_order_available] No bearer token available for ordering schedule check"
                )
                return False

            # Get the full ordering schedule response
            schedule_response = get_ordering_schedule(
                bearer_token=self._toast_bearer_token,
                store_id=self.store_id,
                general_api_endpoint=self.general_api_endpoint,
            )

            # Extract timezone and service periods
            timezone_id = schedule_response.timeZoneId
            service_periods = schedule_response.servicePeriods

            # Check if current time is within service periods
            return is_within_service_periods(
                timezone_id=timezone_id,
                service_periods=service_periods,
                dining_behavior=dining_behavior,
            )

        except Exception as e:
            logger.error(
                f"[ToastTool._is_online_order_available] Error checking if store is open: {e}"
            )
            return False

    # TODO: Decide if we want to register this tool
    def get_ordering_schedule_tool(self) -> str:
        """
        Retrieves the online ordering schedule for a restaurant location.
        Returns information about when the restaurant accepts online orders,
        including service periods, overrides, and scheduling configurations.

        Returns:
            str: A JSON-formatted string containing ordering schedule information including:
                - Service periods with day/time ranges for different dining options
                - Override schedules for special dates (holidays, closures, etc.)
                - Last order configuration (until closing time or with prep time cutoff)
                - Maximum days orders can be placed into the future
                - Restaurant time zone information
        """
        try:
            if not self._toast_bearer_token:
                return (
                    "Failed to authenticate ordering tool. Please reach out to our "
                    "support team at help@palona.ai for assistance."
                )
            schedule_response = get_ordering_schedule(
                bearer_token=self._toast_bearer_token,
                store_id=self.store_id,
                general_api_endpoint=self.general_api_endpoint,
            )

            return parse_service_periods(schedule_response.servicePeriods)

        except Exception as e:
            logger.error(
                f"[ToastTool.get_ordering_schedule_tool] Error retrieving ordering schedule: {e}"
            )
            return "Failed to retrieve ordering schedule information, please try again."

    # TODO: Decide if we want to register this tool
    def get_menu_inventory_tool(self, status: Optional[str] = None) -> str:
        """
        Retrieves current inventory information for menu items from the Toast API.
        Returns inventory details for items that have OUT_OF_STOCK or QUANTITY status.

        Inventory information is not returned for menu items with IN_STOCK status,
        because they are not considered at risk for going out of stock.

        Args:
            status (str, optional): Filter by stock status. Must be either 'OUT_OF_STOCK' or 'QUANTITY'.
                                  If not provided, returns items with both statuses.

        Returns:
            str: A JSON-formatted string containing inventory information including:
                - Item GUID and validity information
                - Current stock status (OUT_OF_STOCK, QUANTITY, etc.)
                - Available quantity for items with quantity tracking
                - Multi-location and version identifiers
        """
        try:
            if not self._toast_bearer_token:
                return (
                    "Failed to authenticate ordering tool. Please reach out to our "
                    "support team at help@palona.ai for assistance."
                )

            # Validate status parameter if provided
            if status and status not in ["OUT_OF_STOCK", "QUANTITY"]:
                return "Invalid status parameter. Status must be either 'OUT_OF_STOCK' or 'QUANTITY'."

            inventory_response = get_menu_inventory(
                bearer_token=self._toast_bearer_token,
                store_id=self.store_id,
                status=status,
            )

            return inventory_response.model_dump_json(indent=2)

        except Exception as e:
            logger.error(
                f"[ToastTool.get_menu_inventory_tool] Error retrieving inventory: {e}"
            )
            return "Failed to retrieve menu inventory information, please try again."

    def _get_existing_order_tool(self) -> Optional[Order]:
        """
        Checks if an existing order is associated with the current conversation.

        Returns:
            Optional[Order]: The existing order if found, otherwise None.

        Raises:
            ValueError: If bearer token is not available.
        """
        if not self._toast_bearer_token:
            raise RuntimeError(
                "[ToastTool._get_existing_order] No bearer token available."
            )

        try:
            return get_existing_order(
                bearer_token=self._toast_bearer_token,
                store_id=self.store_id,
                order_guid=(
                    f"TPC-PALONA:{self.tool_metadata.session_id}"
                    if "sandbox" not in str(self.general_api_endpoint)
                    else f"PALONA:{self.tool_metadata.session_id}"
                ),
                general_api_endpoint=self.general_api_endpoint,
            )

        except Exception as e:
            logger.error(
                f"[ToastTool._get_existing_order] Failed to check for existing order: {e}",
                exc_info=True,
            )
            # Return None to allow order creation to proceed rather than blocking checkout
            return None

    # TODO: decide if we want to use order.externalId for payment intent's externalReferenceId
    # TODO: Add tips
    @tool
    def checkout_order_with_payment_iframe(self) -> str:
        """
        Creates a payment intent for an order with hosted checkout iframe support.

        **WHEN TO USE THIS TOOL:**
        - When the customer has CONFIRMED they want to place/complete their order
        - When the customer says: "checkout", "pay now", "place order", "complete order"
        - When all required ordering information has been collected
        - IMPORTANT: Before using, ask for customer's name and phone number

        **ORDERING PROCESS:**
        1. Customer selects items from the menu
        2. Customer confirms order items, modifiers, and quantities
        3. Ask for customer name and phone number
        4. Customer confirms they want to proceed with payment
        5. Use this tool to create payment intent

        **DO NOT USE WHEN:**
        - Customer is browsing or asking questions
        - Customer is still deciding what to order
        - Customer hasn't confirmed payment
        - Missing customer name and phone number

        Returns:
            str: JSON with payment intent details including sessionSecret for iframe
        """
        try:
            # Check if store is open
            logger.debug(
                "[ToastTool.checkout_order_with_payment_iframe] Checking store status"
            )
            if not self._is_online_order_available():
                return "The store is currently closed for online ordering. Please try again later."

            # Check for existing order
            existing_order = self._get_existing_order_tool()
            if existing_order is not None:
                # Try creating payment intent for existing order if it is not paid yet
                if existing_order.checks[0].paymentStatus in [
                    PaymentStatus.PAID,
                    PaymentStatus.CLOSED,
                ]:
                    return f"Inform the customer their order has been successfully placed and is already paid. Order ID: {existing_order.guid}"
                # Create payment intent for existing order and return payment link
                logger.debug(
                    f"[ToastTool.checkout_order_with_payment_iframe] Found existing unpaid order {existing_order.guid}, creating payment intent"
                )
                price = Price(
                    amount=existing_order.checks[0].amount,
                    taxAmount=existing_order.checks[0].taxAmount,
                    totalAmount=existing_order.checks[0].totalAmount,
                )
                return self._begin_hosted_checkout_flow(existing_order, price)

            # Construct order
            order = self._construct_order()
            if isinstance(order, str):
                return order

            # Validate order
            error_message = self._finalize_order_details(order)
            if error_message:
                return error_message

            price = self._get_order_prices(order=order)

            # Begin hosted checkout flow - payment intent will be created, then order will be submitted
            return self._begin_hosted_checkout_flow(order, price)

        except Exception as e:
            logger.error(f"[ToastTool.checkout_order_with_payment_iframe] Error: {e}")
            logger.error(traceback.format_exc())
            return "Failed to create payment intent. Please try again."

    # TODO: Investigate whether Agno agent can handle async tool calling, and whether calling asynio.run in the tool is allowed
    @tool
    def checkout_order(self) -> str:
        """
        **WHEN TO USE THIS TOOL:**
        - When the customer has CONFIRMED they want to place/complete their order
        - When the customer says things like: "checkout", "pay now", "place order", "complete order", "finalize order"
        - When the customer has finished adding items and is ready to pay
        - When all required ordering information has been collected through the conversation
        - IMPORTANT: Before using this tool, make sure to ask for the customer's name for order pickup

        **ORDERING PROCESS REQUIREMENTS:**
        1. Customer selects items from the menu
        2. Customer confirms their order items, modifiers if any, and quantities
        3. Ask for customer name and phone number (e.g., "Can I get your name and phone number for the order?" or "What's your name and phone number?"), do not ask if they are already provided in the chat history
        4. Customer confirms they want to proceed with payment
        5. THEN use this tool to create the order and payment link

        **DO NOT USE THIS TOOL WHEN:**
        - Customer is just browsing the menu or asking questions
        - Customer is still deciding what to order
        - Customer hasn't confirmed they want to proceed with payment
        - Customer is just asking about prices or availability
        - You haven't asked for the customer's name and phone number yet

        **ONLY USE THIS TOOL ONCE PER ORDER!**

        Returns:
            str: Order checkout confirmation details
        """
        try:
            # First check if the store is open for ordering
            logger.debug(
                "[ToastTool.checkout_order] Checking if the store is open for ordering"
            )
            if not self._is_online_order_available():
                return "The store is currently closed for online ordering. Please try again later."

            # Check if an order with the current conversationId (externalId) already exists.
            # If yes, skip placing a new order and return a message that the order is already successfully placed
            existing_order = self._get_existing_order_tool()
            if existing_order is not None:
                if existing_order.checks[0].paymentStatus in [
                    PaymentStatus.PAID,
                    PaymentStatus.CLOSED,
                ]:
                    return f"Your order has been successfully placed and is already paid. Order ID: {existing_order.guid}"
                return f"Your order has been created but payment is still pending. Order ID: {existing_order.guid}. Please complete payment to finalize your order."

            order = self._construct_order()

            # If the order is a string, it indicates an error message
            # In this case, return the error message
            if isinstance(order, str):
                return order

            # Validate and check the order
            error_message = self._finalize_order_details(order)
            if error_message:
                return error_message

            result = self._submit_order(order)

            # Handle both success (tuple) and error (string) cases
            if isinstance(result, tuple):
                order, confirmation_message = result
                return confirmation_message
            else:
                # Error message string
                return result

        except Exception as e:
            logger.error(f"[ToastTool.checkout_order] Error in submit order: {e}")
            logger.error(traceback.format_exc())
            return "Please try again."

    @retrieval
    def _get_chat_history(self) -> str:
        """
        Retrieves the chat history from the query messages tool.

        Returns:
            str: A string representing the entire chat history.
        """
        # TODO: The query_messages function returns error messages rather than raising exceptions. There is no generic way to verify the validity of the returned chat_history.
        chat_history: str = self.query_messages_tool.query_messages()  # type: ignore

        # Basic check for error messages (TEMPORARY workaround)
        error_indicators = [
            "Error in getting chat history",
            "Conversation history not found",
            "Agent session not found",
        ]
        if any(indicator in chat_history for indicator in error_indicators):
            logger.warning(
                f"[ToastTool._get_chat_history] Possible issue with chat history: {chat_history}"
            )

        LLMObs.annotate(output_data=chat_history)

        return chat_history

    @retrieval
    def _get_relevant_docs(self, chat_history: str) -> str:
        # Check if query engine is available
        if self.query_engine is None:
            return "Menu information is not available for this store."

        # Decompose chat history into multiple sub-queries
        sub_queries = llm_call(
            system_prompt=self.backdoor_tool_prompt.get(
                "order_item_prompt", RETRIEVE_ORDER_ITEMS_SYSTEM_PROMPT
            ),
            prompt=chat_history,
            response_format=SubQueries,
            openai=False,
        )

        # Append dining options to the sub-queries
        if isinstance(sub_queries, SubQueries):
            sub_queries.queries.append("dining options")

        if not isinstance(sub_queries, SubQueries):
            return "Failed to identify the items the user ordered in the conversation."

        logger.debug(f"Sub-queries identified: {sub_queries.queries}")

        async def run_all_queries():
            assert self.query_engine is not None  # Already checked above
            tasks = [
                asyncio.create_task(self.query_engine.aquery(query))
                for query in sub_queries.queries
            ]
            try:
                return await asyncio.gather(*tasks)
            except Exception:
                # Cancel remaining tasks
                for task in tasks:
                    if not task.done():
                        task.cancel()
                # Wait for all tasks to complete cancellation (optional)
                await asyncio.gather(*tasks, return_exceptions=True)
                raise

        # Use asyncio.run for a simple async execution without need for manual event loop management
        try:
            results = asyncio.run(run_all_queries())
        except Exception as e:
            logger.error(f"[ToastTool._get_relevant_docs] Error executing queries: {e}")
            # Raise exception when it throws error as no documents were retrieved
            raise RuntimeError(
                "[ToastTool._get_relevant_docs] run_all_queries failed to retrieve relevant documents."
            ) from e

        context = ""
        output_data = []
        found_doc_names = set()
        found_dining_options = False
        # Iterate through the results and extract relevant information
        for res in results:
            for node in res.source_nodes:
                if node.metadata:
                    # Check if this is a dining options document
                    is_dining_options = node.metadata.get("isDiningOptions", False)

                    # Indent the text
                    node_text = textwrap.indent(node.text, 2 * "\t")
                    # If the metadata isDiningOptions boolean is True, prepend the DINING_OPTIONS_INSTRUCTION to the node_text
                    if is_dining_options:
                        found_dining_options = True
                        dining_options_text = self.backdoor_tool_prompt.get(
                            "dining_options_prompt", DINING_OPTIONS_INSTRUCTION
                        )
                        node_text = (
                            textwrap.indent(
                                dining_options_text,
                                2 * "\t",
                            )
                            + "\n"
                            + node_text
                        )
                        doc_name = node.metadata.get("file_name", "dining_options.txt")
                    else:
                        doc_name = node.metadata.get(
                            "file_name", f"document_{node.id_}"
                        )

                    # Check if the document name is already in the set
                    # If it is, skip to the next node
                    # If not, add it to the set and process the node
                    if doc_name in found_doc_names:
                        continue
                    found_doc_names.add(doc_name)

                    context += (
                        f"<document name='{doc_name}'>\n"
                        "\t<document_content>\n"
                        f"{node_text}\n"
                        "\t</document_content>\n"
                        "</document>\n\n"
                    )
                    output_data.append({"id": node.id_, "text": node.text})

        # Check if dining options were found
        if not found_dining_options:
            logger.error(
                "[ToastTool._get_relevant_docs] Dining options file not found in menu knowledge base"
            )
            raise ValueError(
                "Dining options file not found in the menu knowledge base."
            )

        LLMObs.annotate(input_data=chat_history, output_data=output_data)
        return context

    @staticmethod
    def _is_invalid_guid(guid) -> bool:
        """Check if a GUID is invalid (None, 'N/A', empty, or whitespace-only)."""
        return guid in (None, "N/A", "") or (isinstance(guid, str) and not guid.strip())

    def _get_valid_modifiers(self, mods: list[Modifier]) -> list[Modifier]:
        """Remove modifiers with invalid or missing GUIDs. Processes nested modifiers recursively."""
        cleaned: list[Modifier] = []
        for m in mods:
            # Basic validation: require both GUIDs (reject None, "N/A", empty, or whitespace-only)
            if m.selectionType == SelectionType.SPECIAL_REQUEST:
                cleaned.append(m)
                continue

            og_guid = getattr(m.optionGroup, "guid", None)
            it_guid = getattr(m.item, "guid", None)

            if self._is_invalid_guid(og_guid) or self._is_invalid_guid(it_guid):
                continue

            # Recursively clean nested modifiers or normalize to empty list for Toast API
            nested_mods = getattr(m, "modifiers", None)
            m.modifiers = self._get_valid_modifiers(nested_mods) if nested_mods else []
            cleaned.append(m)
        return cleaned

    def _remove_invalid_modifiers(self, order: OrderInput) -> OrderInput:
        """Remove invalid modifiers from all items in the order."""
        try:
            for check in order.checks:  # type: ignore
                for selection in check.selections:
                    if selection.modifiers:
                        selection.modifiers = self._get_valid_modifiers(
                            list(selection.modifiers)
                        )

            return order

        except Exception as e:
            logger.error(
                "[ToastTool._remove_invalid_modifiers] "
                f"Error in removing invalid modifiers: {e}"
            )
            raise e

    def _construct_order(self) -> OrderInput | str:
        chat_history: str = self._get_chat_history()  # type: ignore
        context = self._get_relevant_docs(chat_history)  # type: ignore

        # Get current date and time in the store's timezone
        store_tz = self.tool_metadata.timezone or "America/Los_Angeles"
        current_dt_store = datetime.now(ZoneInfo(store_tz))

        # Add current date/time to context for LLM to understand temporal references
        current_time_info = (
            f"\n\n<current_datetime>\n"
            f"Current date and time: {current_dt_store.strftime('%A, %B %d, %Y at %I:%M %p')} ({store_tz})\n"
            f"Use timezone: {store_tz}\n"
            f"</current_datetime>"
        )
        context += current_time_info  # type: ignore

        # Get prompt overrides or defaults
        system_prompt = self.backdoor_tool_prompt.get(
            "system_prompt", EXTRACTOR_SYSTEM_PROMPT
        )
        user_prompt_template = self.backdoor_tool_prompt.get(
            "user_prompt", EXTRACTOR_USER_PROMPT
        )

        order = llm_call(
            system_prompt=system_prompt,
            prompt=user_prompt_template.format(
                context=context, chat_history=chat_history
            ),
            response_format=OrderInput,
            openai=True,
            order_construction_model=self.order_construction_model,
        )
        print(f"Raw constructed order: {order}")
        # Check if the order is a string and convert it to an OrderInput object, catching any errors
        try:
            if order is None:
                raise ValueError("Order is None")

            if type(order) is str:
                order = json.loads(order)
                order = OrderInput(**order)

            # Validate modifiers in the order
            order = self._remove_invalid_modifiers(order)

            if not isinstance(order, OrderInput):
                raise ValueError(
                    f"`order` object in type {type(order)} but expected type Order.\n"
                    f"`order` object: {order}"
                )
            logger.debug(f"[ToastTool._construct_order] Constructed order: {order}")

            # Note: lastName suffix will be added in _finalize_order_details after validation

            return order
        except ValidationError as e:
            logger.warning(e)
            warning_message = ""
            for error in e.errors():
                logger.warning(
                    f"Missing or invalid order data in the response: {error}"
                )
                warning_message += f"Missing or invalid order data in the response: {error['loc'][-1]}: {error['msg']}, input: {error.get('input', 'N/A')}\n"
            return (
                warning_message
                + "\nAsk the customer to provide the missing information or correct the invalid details."
            )
        except Exception as e:
            logger.error(e)
            return f"Failed to construct order: {e}"

    def _finalize_order_details(self, order: OrderInput) -> str | None:
        """
        Validate order requirements and add agent suffix to customer lastName.

        Checks: dining option, customer info (name, email, phone), and authentication.

        Returns:
            str | None: Error message if validation fails, None if successful.
        """
        # Check if the order type non-empty and takeout. For now, we only support takeout orders

        if not order.diningOption or not order.diningOption.guid:
            logger.warning(
                "[ToastTool._finalize_order_details] Order diningOption is missing or its guid is empty."
            )
            return "Sorry, do you want that for Takeout? We only support Takeout orders at the moment."

        try:
            _ = validate_item_modifier_quantity(order.checks[0].selections)
        except Exception as e:
            logger.error(
                f"[ToastTool._finalize_order_details] Could not validate order type: {e}"
            )
            return "Sorry, do you want that for Takeout? We only support Takeout orders at the moment."

        # TODO: Validate the address if the order is for delivery
        # PLACEHOLDER: Validate the address if the order is for delivery

        # Handle scheduled orders: validate and set openedDate to match promisedDate
        if order.promisedDate:
            try:
                # Validate ISO 8601 format by parsing
                datetime.fromisoformat(order.promisedDate)

                # Set openedDate to match promisedDate for scheduled orders
                order.openedDate = order.promisedDate

                logger.debug(
                    f"[ToastTool._finalize_order_details] Scheduled order: "
                    f"promisedDate={order.promisedDate}, openedDate={order.openedDate}"
                )
            except ValueError as e:
                logger.error(
                    f"[ToastTool._finalize_order_details] Invalid promisedDate format: {e}"
                )
                return f"Invalid scheduled time format: {str(e)}. Please provide the time in a valid format (e.g., '2025-05-01T14:30:00.000-0800')."
            except Exception as e:
                logger.error(
                    f"[ToastTool._finalize_order_details] Error processing scheduled order: {e}"
                )
                return f"Error processing scheduled order: {str(e)}"

        # Add revenue center id if it is provided
        if self.revenue_center_id:
            order.revenueCenter = {"guid": self.revenue_center_id}

        logger.debug(
            f"[ToastTool._finalize_order_details] Extracted structured data: {order}"
        )

        ### Validate checks ###
        if not order.checks:
            logger.error(
                "[ToastTool._finalize_order_details] Order checks are missing."
            )
            return "We'll need to check your order to place it."

        # Validate each check in the order
        for check in order.checks:
            if not check.customer:
                logger.warning(
                    "[ToastTool._finalize_order_details] Customer info is missing."
                )
                return "We'll need your first name, last name, email, and phone number to place the order."
            if not check.customer.firstName:
                logger.warning(
                    "[ToastTool._finalize_order_details] Customer first name is missing."
                )
                return "We'll need your first name."
            if not check.customer.lastName:
                logger.warning(
                    "[ToastTool._finalize_order_details] Customer last name is missing."
                )
                return "We'll need your last name."

            email = check.customer.email
            if not email or not is_valid_email(email):
                logger.warning(
                    f"[ToastTool._finalize_order_details] Invalid email address: {email}"
                )
                return "We'll need your email address."

            ########## NOTE: the following is how Adora agent handles the email. ##########
            # Set email to default if empty or if it is not valid
            # email = order.customer.email
            # if not email or not is_valid_email(email):
            #     order.customer.email = "jimmythesurfer@palona.ai"
            ##############################################

            if not check.customer.phone or not is_valid_phone_number(
                format_phone_number(check.customer.phone)
            ):
                logger.warning(
                    f"[ToastTool._finalize_order_details] Customer phone number is missing or invalid. Phone: {check.customer.phone}"
                )
                return "We'll need your phone number."

            # Add suffix to lastName after all validation passes
            # Append if lastName is not user provided
            if check.customer.lastName and check.customer.lastName.strip():
                trimmed_lastname = check.customer.lastName.strip()
                if VIA_AGENT_SUFFIX not in trimmed_lastname:
                    check.customer.lastName = f"{trimmed_lastname} {VIA_AGENT_SUFFIX}"

            # Add tabName to check
            setattr(check, "tabName", f"PalonaAI_{self.tool_metadata.session_id}")

    def _submit_order(self, order: OrderInput) -> str | tuple[Order, str]:
        # Retrieve the bearer token
        toast_bearer_token = self._toast_bearer_token
        if not toast_bearer_token:
            return (
                "Failed to authenticate ordering tool. "
                "Please reach out to our support team at help@palona.ai "
                "for assistance."
            )
        # First let toast API fill in the prices
        try:
            # Set the order externalId to the session id to track the order
            order.externalId = (
                f"TPC-PALONA:{self.tool_metadata.session_id}"
                if "sandbox" not in str(self.general_api_endpoint)
                else f"PALONA:{self.tool_metadata.session_id}"
            )
            order = submit_order(
                toast_bearer_token,
                self.store_id,
                order,
                general_api_endpoint=self.general_api_endpoint,
            )

            # TODO: Decide what messages to return to the user, and whether we want to store the Order guid in the database.
            logger.debug(
                f"[ToastTool._submit_order] Order #{order.guid} submitted successfully! External ID: {order.externalId}. Your total is ${order.checks[0].totalAmount}. Your order summary: {order.checks[0].selections}.\n\nYour order will be ready for pickup at {order.estimatedFulfillmentDate}"
            )
            return (
                order,
                f"Order #{order.externalId} submitted successfully! "
                f"Your total is ${order.checks[0].totalAmount}. "
                f"Your order summary: {order.checks[0].selections}.\n\n"
                f"Your order will be ready for pickup at {order.estimatedFulfillmentDate}",
            )
        except Exception as e:
            logger.error(f"[ToastTool._submit_order] Failed to submit the order: {e}")
            return "There was an error while submitting the order. Please try again."

    def _get_order_prices(self, order: OrderInput) -> Price:
        # Retrieve the bearer token
        toast_bearer_token = self._toast_bearer_token
        if not toast_bearer_token:
            logger.error(
                "[ToastTool._get_order_prices] Toast bearer token is missing or invalid"
            )
            raise ValueError(
                "[ToastTool._get_order_prices] Toast bearer token is missing or invalid. "
                "Please reach out to our support team at help@palona.ai "
                "for assistance."
            )
        try:
            order_wt_prices = get_order_prices(
                toast_bearer_token,
                self.store_id,
                order,
                general_api_endpoint=self.general_api_endpoint,
            )

            applied_service_charges: list[AppliedServiceCharge] | None = None
            check_dict = order_wt_prices.checks[0].model_dump()
            if (
                "appliedServiceCharges" in check_dict
                and check_dict["appliedServiceCharges"]
            ):
                applied_service_charges = [
                    AppliedServiceCharge(**charge)
                    for charge in check_dict["appliedServiceCharges"]
                ]

            return Price(
                amount=order_wt_prices.checks[0].amount,
                taxAmount=order_wt_prices.checks[0].taxAmount,
                totalAmount=order_wt_prices.checks[0].totalAmount,
                appliedServiceCharges=applied_service_charges,
            )
        except Exception as e:
            logger.error(
                f"[ToastTool._get_order_prices] Failed to get the order prices: {e}"
            )
            raise

    def _calculate_gratuity_fee(
        self,
        *,
        order: Order | OrderInput,
        price: Price | None,
    ) -> list[dict[str, Any]]:
        """
        Calculates the gratuity fees for an order based on dining behavior and gratuity flags.

        Returns a list of fee items where each item has:
        - name: The name of the fee (from appliedServiceCharge.name)
        - total: The fee amount in cents (for display)

        Includes charges where:
        - For delivery orders: delivery=True OR gratuity=True
        - For takeout orders: takeout=True OR gratuity=True
        - For other dining behaviors: only gratuity=True charges

        Args:
            order: The Order or OrderInput object containing dining option info
            price: Price object containing applied service charges

        Returns:
            list[dict[str, Any]]: List of fee items with {name: str, total: int (cents)}
        """
        if not price or not price.appliedServiceCharges:
            return []

        behavior = order.diningOption.behavior
        is_delivery = behavior == DiningBehavior.DELIVERY
        is_takeout = behavior == DiningBehavior.TAKE_OUT

        fees: list[dict[str, Any]] = []

        for charge in price.appliedServiceCharges:
            if not charge.chargeAmount:
                continue

            should_include = False

            # Check gratuity flag first (applies to all order types)
            if charge.gratuity:
                should_include = True
            # Then check delivery/takeout flags based on order type
            elif is_delivery and charge.delivery:
                should_include = True
            elif is_takeout and charge.takeout:
                should_include = True

            if should_include:
                fees.append(
                    {
                        "name": charge.name or "Fee",
                        "total": int(charge.chargeAmount * 100),
                    }
                )

        return fees

    @tool
    def get_order_prices_tool(self) -> Price:
        """
        Gets pricing information for the current order.

        Args:
            None

        Returns:
            Price: Price object containing pricing details (amount, taxAmount, totalAmount)
        """
        try:
            order = self._construct_order()

            # If the order is a string, it indicates an error message
            # In this case, raise an exception with the error message
            if isinstance(order, str):
                raise ValueError(f"Failed to construct order: {order}")

            return self._get_order_prices(order)
        except Exception as e:
            logger.error(
                f"[ToastTool.get_order_prices_tool] Error in get order prices: {e}"
            )
            raise

    def _create_payment_intent(
        self,
        price: Price,
        external_reference_id: str | None = None,
        payments_api_endpoint: str | None = None,
    ) -> PaymentIntentResponse | str:
        """
        Creates a payment intent with the given price information.

        Args:
            price: Price object containing amount, taxAmount, and totalAmount
            external_reference_id: Optional unique identifier for this payment
            payments_api_endpoint: Optional custom payments API endpoint

        Returns:
            PaymentIntentResponse with session secret, or error message string
        """
        # Get bearer token
        toast_bearer_token = self._toast_hosted_payment_checkout_bearer_token
        if not toast_bearer_token:
            return (
                "Failed to authenticate ordering tool. "
                "Please reach out to our support team at help@palona.ai "
                "for assistance."
            )

        try:
            # Calculate total amount in cents (use round() to avoid float truncation issues)
            total_amount_cents = round(price.totalAmount * 100)  # type: ignore

            if not external_reference_id:
                external_reference_id = str(uuid.uuid4())

            # Create payment intent request
            payment_request = PaymentIntentRequest(
                amount=total_amount_cents,
                amountDetails={
                    "tip": 0
                },  # TODO: Set tip to 0 for now. Later we can consider asking the user for tip amount.
                currency="USD",
                externalReferenceId=external_reference_id,
                captureMethod="MANUAL",
            )

            # Create payment intent
            payment_intent_response = create_payment_intent(
                bearer_token=toast_bearer_token,
                store_id=self.store_id,
                payment_request=payment_request,
                payments_api_endpoint=payments_api_endpoint,  # Use default sandbox endpoint
            )

            logger.debug(
                f"[ToastTool._create_payment_intent] Created payment intent: ID: {payment_intent_response.id}. Payment intent external Reference ID: {payment_intent_response.externalReferenceId}."
            )

            return payment_intent_response

        except Exception as e:
            logger.error(
                f"[ToastTool._create_payment_intent] Error creating payment intent: {e}"
            )
            return "Failed to create payment intent. Please try again."

    def _begin_hosted_checkout_flow(self, order: OrderInput, price: Price) -> str:
        """
        Begins the hosted checkout flow for an order with priced information.

        This method handles the complete payment flow:
        1. Creates a payment intent with the calculated price information
        2. Submits the order to Toast
        3. Extracts order items from the submitted order
        4. Builds the payment payload with order details
        5. Generates and returns the hosted payment iframe link

        If order submission fails after payment intent creation, the payment intent
        will remain orphaned. A new payment intent can be created on subsequent calls.

        Args:
            order: OrderInput object to be submitted to Toast.
                   For existing unpaid orders, pass the Order object.
            price: Price object containing calculated pricing (amount, taxAmount, totalAmount).

        Returns:
            str: Formatted message with payment link for the customer
        """
        # Create payment intent
        payment_intent_external_reference_id = str(uuid.uuid4())
        payment_intent_result = self._create_payment_intent(
            price, external_reference_id=payment_intent_external_reference_id
        )
        # If payment intent result is a string, it indicates an error message
        if isinstance(payment_intent_result, str):
            return payment_intent_result

        # After payment intent is successfully created, submit the order
        result = self._submit_order(order)

        # Handle both success (tuple) and error (string) cases
        if isinstance(result, tuple):
            order, _ = result
        else:
            # If result is a string, it indicates an error message
            return result

        # Check if order.externalId is set after successful order submission. This absolutely must not be empty because we need it later to update the order's check.
        if order.externalId is None:
            raise ValueError("Order externalId is None after submission")

        # Extract order items from the submitted order
        order_items = self._extract_order_items(order)
        logger.debug(
            f"[ToastTool._begin_hosted_checkout_flow] Extracted {len(order_items)} order items"
        )

        # Create a concise order summary from extracted items
        order_summary_lines = []
        for item in order_items:
            item_line = f"- {item['name']} (x{item['quantity']})"
            if item.get("modifiers"):
                # If modifiers is a list of strings
                if isinstance(item["modifiers"], list) and item["modifiers"]:
                    if isinstance(item["modifiers"][0], str):
                        mods = ", ".join(item["modifiers"])
                    else:
                        # If modifiers is a list of dicts
                        mods = ", ".join(
                            [
                                m.get("name", "")
                                for m in item["modifiers"]
                                if m.get("name")
                            ]
                        )
                    if mods:
                        item_line += f" [{mods}]"
            order_summary_lines.append(item_line)

        order_summary = "\n".join(order_summary_lines)

        # Calculate gratuity fees for the payment payload (list of {name, total} items)
        gratuity_fees = self._calculate_gratuity_fee(order=order, price=price)

        # Create concise confirmation message using extracted order items
        concise_confirmation = (
            f"Order #{order.externalId} submitted successfully! "
            f"Your total is ${order.checks[0].totalAmount}.\n"
            f"You can find tax and any applicable fees on the payment page.\n\n"
            f"Order summary:\n{order_summary}\n\n"
            f"Your order will be ready for pickup at {order.estimatedFulfillmentDate}"
        )

        # Build hosted payment payload
        payment_payload = self._build_hosted_payment_payload(
            order=order,
            payment_intent_id=payment_intent_result.id,
            payment_intent_external_reference_id=payment_intent_external_reference_id,
            session_secret=payment_intent_result.sessionSecret,
            payment_intent_amount=payment_intent_result.amount,
            order_items=order_items,
            gratuity_fees=gratuity_fees,
        )

        # Generate iframe payment link
        payment_link = self._generate_iframe_payment_link(payment_payload)

        # Return payment intent details with concise confirmation
        return_msg = (
            concise_confirmation
            + f"\n\nThe following is the payment link, ask the user to use the link to checkout, tell the customer the link will expire in {self.payment_iframe_token_ttl_seconds // 60} minutes.: {payment_link}\n\nYou MUST INCLUDE THE COMPLETE URL in your response and format it as a Markdown link. For example, [payment link](COMPLETE_URL_HERE) YOU MUST NOT OMIT ANY PART OF THE URL. "
        )
        return return_msg

    def _build_hosted_payment_payload(
        self,
        *,
        order: Order,
        payment_intent_id: str,
        payment_intent_external_reference_id: str,
        session_secret: str,
        payment_intent_amount: int,
        order_items: list[dict[str, Any]] | None = None,
        gratuity_fees: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Builds the payload for the hosted payment iframe.

        Args:
            order: The submitted Toast Order object
            payment_intent_id: The actual Toast payment intent ID (used for updatePaymentIntent API)
            payment_intent_external_reference_id: External reference ID for the payment intent
            session_secret: Session secret from the payment intent
            payment_intent_amount: Total amount for the payment intent in cents
            order_items: Extracted order items for cart display
            gratuity_fees: List of gratuity fee items with {name: str, total: int (cents)}

        Returns:
            Dictionary containing all payment payload data
        """
        customer = order.checks[0].customer
        full_name = (customer.firstName + " " + customer.lastName).strip()

        # Get iframe bearer token for frontend to initialize Toast payment widget
        payment_api_endpoint = (
            "https://ws-sandbox-api.eng.toasttab.com"
            if self.sandbox
            else "https://ws-api.toasttab.com"
        )

        iframe_bearer_token = get_toast_access_token_from_aws(
            token_api_endpoint=payment_api_endpoint,
            token_name="TOAST_PAYMENT_IFRAME_ACCESS_TOKEN",
            credential_name="TOAST_PAYMENT_IFRAME_CLIENT_CREDENTIALS",
        )
        if not iframe_bearer_token:
            raise ValueError(
                "[ToastTool._build_hosted_payment_payload] Failed to retrieve iframe bearer token."
            )

        payload: dict[str, Any] = {
            "email": customer.email,
            "name": full_name,
            "phone": customer.phone,
            "storeId": self.store_id,
            "orderExternalId": order.externalId,
            "paymentIntentId": payment_intent_id,
            "paymentIntentExternalReferenceId": payment_intent_external_reference_id,
            "subtotal": (
                round(order.checks[0].amount * 100) if order.checks[0].amount else 0
            ),
            "tax": (
                round(order.checks[0].taxAmount * 100)
                if order.checks[0].taxAmount
                else 0
            ),
            "gratuityFees": gratuity_fees or [],
            "total": payment_intent_amount,
            "tips": 0,
            "sessionSecret": session_secret,
            "iframeBearerToken": iframe_bearer_token.access_token,
            "orderItems": order_items or [],
            "expiresAt": int(time.time()) + self.payment_iframe_token_ttl_seconds,
        }

        logger.debug(
            "[ToastTool._build_hosted_payment_payload] Payload composed",
            extra={
                "store_id": payload["storeId"],
                "order_external_id": payload["orderExternalId"],
                "order_items": len(payload["orderItems"]),
                "gratuity_fees_count": len(payload["gratuityFees"]),
            },
        )

        return payload

    def _generate_iframe_payment_link(
        self,
        payload: dict[str, Any],
    ) -> str:
        """
        Generates a hosted payment iframe link with encrypted payload.

        Uses Fernet encryption to securely store the entire payload (including orderItems)
        in a short token. The frontend will decrypt this via backend API endpoint.

        Args:
            payload: Complete payment payload dictionary including expiresAt timestamp

        Returns:
            str: The URL for the hosted payment iframe with encrypted token
        """
        try:
            # Encrypt the entire payload using Fernet (includes orderItems and expiresAt timestamp)
            token_bytes = self._payment_iframe_fernet.encrypt(
                json.dumps(payload).encode("utf-8")
            )
            token = urllib.parse.quote(token_bytes.decode("utf-8"))

            # Construct the iframe URL with encrypted token
            iframe_url = f"{self.hosted_payment_iframe_endpoint}?t={token}"

            logger.debug(
                "[ToastTool._generate_iframe_payment_link] Generated iframe URL with encrypted token",
                extra={
                    "hosted_endpoint": self.hosted_payment_iframe_endpoint,
                    "token_length": len(token),
                    "url_length": len(iframe_url),
                },
            )

            shortened_url = shorten_url(iframe_url)
            return shortened_url

        except Exception as e:
            logger.error(
                f"[ToastTool._generate_iframe_payment_link] Error generating iframe payment link: {e}"
            )
            traceback.print_exc()
            return "Failed to generate payment link. Please try again."

    def _extract_order_items(self, order: Order) -> list[dict[str, Any]]:
        """
        Extracts order items from a Toast Order object into a simplified cart format.

        Args:
            order: Toast Order object returned from submit_order

        Returns:
            List of dictionaries containing simplified cart items with modifiers
        """
        if not order or not order.checks:
            return []

        order_items: list[dict[str, Any]] = []

        # Convert Order to dict to access extra fields that aren't in the Pydantic model
        order_dict = order.model_dump()

        # Debug: Log the first selection to see what fields are available
        if order_dict.get("checks") and order_dict["checks"][0].get("selections"):
            first_selection = order_dict["checks"][0]["selections"][0]
            logger.debug(
                f"[ToastTool._extract_order_items] First selection keys: {list(first_selection.keys())}"
            )
            logger.debug(
                f"[ToastTool._extract_order_items] First selection displayName: {first_selection.get('displayName')}"
            )
            logger.debug(
                f"[ToastTool._extract_order_items] First selection item guid: {first_selection.get('item', {}).get('guid')}"
            )

        # Toast orders have checks, and each check has selections (items)
        for check_dict in order_dict.get("checks", []):
            selections = check_dict.get("selections", [])
            if not selections:
                continue

            for selection in selections:
                # Extract item name from displayName or fallback to item guid
                name = selection.get("displayName")
                if not name:
                    # Fallback to item guid if displayName is not available
                    item = selection.get("item", {})
                    item_guid = item.get("guid") if item else None
                    name = str(item_guid) if item_guid else "Unknown Item"

                # Get pricing information with fallbacks
                receipt_price = selection.get("receiptLinePrice")
                pre_discount_price = selection.get("preDiscountPrice")
                totalcost = (
                    receipt_price if receipt_price is not None else pre_discount_price
                )

                # Create the base item entry
                entry: dict[str, Any] = {
                    "name": name,
                    "quantity": selection.get("quantity", 1),
                    "totalcost": totalcost,
                }

                # Add special instructions if available
                special_instructions = selection.get("specialinstructions")
                if special_instructions:
                    entry["specialinstructions"] = special_instructions

                # Extract modifiers recursively
                modifiers = selection.get("modifiers", [])
                if modifiers:
                    modifier_entries = self._extract_modifiers_recursive_from_dict(
                        modifiers
                    )
                    if modifier_entries:
                        entry["modifiers"] = modifier_entries

                order_items.append(entry)

        return order_items

    def _extract_modifiers_recursive_from_dict(
        self, modifiers: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Recursively extracts modifiers from a list of modifier dictionaries.

        Args:
            modifiers: List of modifier dictionaries from Order response

        Returns:
            List of dictionaries containing simplified modifier information
        """
        modifier_entries: list[dict[str, Any]] = []

        for modifier in modifiers:
            # Extract modifier name from displayName or fallback to item guid
            modifier_name = modifier.get("displayName")
            if not modifier_name:
                # Fallback to item guid if displayName is not available
                item = modifier.get("item", {})
                item_guid = item.get("guid") if item else None
                modifier_name = str(item_guid) if item_guid else "Unknown Modifier"

            modifier_entry: dict[str, Any] = {
                "name": modifier_name,
                "quantity": modifier.get("quantity", 1),
            }

            # Add price information if available
            receipt_price = modifier.get("receiptLinePrice")
            pre_discount_price = modifier.get("preDiscountPrice")
            if receipt_price is not None:
                modifier_entry["totalcost"] = receipt_price
            elif pre_discount_price is not None:
                modifier_entry["totalcost"] = pre_discount_price

            # Recursively handle nested modifiers
            nested_modifiers = modifier.get("modifiers", [])
            if nested_modifiers:
                nested_modifier_entries = self._extract_modifiers_recursive_from_dict(
                    nested_modifiers
                )
                if nested_modifier_entries:
                    modifier_entry["modifiers"] = nested_modifier_entries

            modifier_entries.append(modifier_entry)

        return modifier_entries
