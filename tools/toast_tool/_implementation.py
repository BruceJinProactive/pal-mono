import asyncio
import json
import textwrap
import time
import traceback
import uuid
from typing import Optional

import jwt
import polyline
from agno.tools.toolkit import Toolkit
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import rsa
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import retrieval, tool
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
    DeliveryAddress,
    DiningBehavior,
    Modifier,
    Order,
    OrderInput,
    PaymentIntentRequest,
    PaymentIntentResponse,
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
from utils.log import logger

# Agent identification suffix for customer names
VIA_AGENT_SUFFIX = "(via PalonaAI)"


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
        token_api_endpoint: str | None = None,
        general_api_endpoint: str | None = None,
        sandbox: bool = False,
        hosted_payment_iframe_endpoint: str = "http://localhost:3000/checkout/toast",
        enable_hosted_checkout: bool = False,
    ):
        super().__init__(name="toast_tool")

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

        # Register tools
        if self.enable_hosted_checkout:
            self.register(self.checkout_order_with_payment_intent)
        else:
            self.register(self.checkout_order)

        # Do not register get_menu_inventory_tool and get_ordering_schedule_tool for now
        self.register(self.get_ordering_schedule_tool)
        self.register(self.is_online_order_available)
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

    def check_address(self, address: str) -> str:
        """
        Validates if the given address (using x and y coordinates) is within the restaurant's delivery area.
        Retrieves the store information (from cache or API), accesses the delivery area using dot notation,
        decodes the polyline string into a list of Point objects, and creates a Polygon instance.
        Finally, it checks whether the provided point lies inside the polygon area.
        Args:
            address (str): The address to validate.
        Returns:
            str: A message indicating whether the address is within the delivery area.
        """
        # Retrieve store information from cache if available.

        if not address:
            return "Could you provide your address?"

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

        success, message, delivery_address = add_lat_long_to_address(delivery_address)
        if not success:
            return message

        point = Point(delivery_address.lng, delivery_address.lat)
        store_info_str = self.get_store_info()
        if store_info_str == "Failed to get the store information, please try again.":
            return store_info_str
        try:
            store_info = json.loads(store_info_str)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse store info JSON: {e}")
            return "Failed to process store information."

        polyline_str = (
            store_info["delivery"]["area"]
            if "delivery" in store_info and "area" in store_info["delivery"]
            else None
        )
        if (
            not polyline_str
            or polyline_str == "Failed to get the store information, please try again."
        ):
            return "Delivery area is empty." if not polyline_str else polyline_str

        # Decode the polyline string into a list of Point objects
        try:
            decoded = polyline.decode(polyline_str, geojson=True)
            polygon = Polygon([(lng, lat) for lng, lat in decoded])
        except Exception as e:
            logger.error(f"Decode polyline to points failed: {e}")
            return "Failed to decode the delivery area boundary."

        # Validate the given point against the polygon's area using our helper method
        if polygon.contains(point):
            return "Address is within the delivery area."
        else:
            return "Address is outside the delivery area."

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
                order_guid=f"TPC-PALONA:{self.tool_metadata.session_id}",
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
    def checkout_order_with_payment_intent(self) -> str:
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
                "[ToastTool.checkout_order_with_payment_intent] Checking store status"
            )
            if not self._is_online_order_available():
                return "The store is currently closed for online ordering. Please try again later."

            # Check for existing order
            if self._get_existing_order_tool() is not None:
                return "Your order has been successfully placed."

            # Construct order
            order = self._construct_order()
            if isinstance(order, str):
                return order

            # Validate order
            error_message = self._finalize_order_details(order)
            if error_message:
                return error_message

            result = self._submit_order(order)

            # Handle both success (tuple) and error (string) cases
            if isinstance(result, tuple):
                order, confirmation_message = result
            else:
                # If result is a string, it indicates an error message
                return result

            # Create payment intent
            payment_intent_external_reference_id = str(uuid.uuid4())
            payment_intent_result = self._create_payment_intent_for_order(
                order, external_reference_id=payment_intent_external_reference_id
            )
            # If payment intent result is a string, it indicates an error message
            if isinstance(payment_intent_result, str):
                return payment_intent_result

            # Check if order.externalId is set after successful order submission. This absolutely must not be empty because we need it later to update the order's check.
            if order.externalId is None:
                raise ValueError("Order externalId is None after submission")

            # Sanity check for iframe bearer token
            toast_hosted_payment_iframe_bearer_token = (
                self._toast_hosted_payment_iframe_bearer_token
            )
            if not toast_hosted_payment_iframe_bearer_token:
                logger.error(
                    "[ToastTool.checkout_order_with_payment_intent] No hosted checkout payment bearer token available"
                )
                return "Failed to authenticate payment tool. Please contact the store to complete your order."

            # Generate iframe payment link
            payment_link = self._generate_iframe_payment_link(
                order.checks[0].customer.email,
                self.store_id,
                order.externalId,
                payment_intent_external_reference_id,
                payment_intent_result.sessionSecret,
                subtotal_cents=payment_intent_result.amount,
                tips_cents=0,
            )

            # Return payment intent details
            return_msg = (
                confirmation_message
                + f"\n\nThe following is the payment link, ask the user to use the link to checkout: [payment link]({payment_link})\n\nYou MUST INCLUDE THE COMPLETE URL in your response, formatted as a Markdown link. YOU MUST NOT OMIT ANY PART OF THE URL."
            )
            return return_msg

        except Exception as e:
            logger.error(f"[ToastTool.checkout_order_with_payment_intent] Error: {e}")
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
            if_order_exists = self._get_existing_order_tool() is not None
            if if_order_exists:
                return "Your order has been successfully placed."

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
            system_prompt=RETRIEVE_ORDER_ITEMS_SYSTEM_PROMPT,
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
            results = []

        context = ""
        output_data = []
        found_doc_names = set()
        # Iterate through the results and extract relevant information
        for res in results:
            for node in res.source_nodes:
                if node.metadata:
                    # Indent the text
                    node_text = textwrap.indent(node.text, 2 * "\t")
                    # If the metadata isDiningOptions boolean is True, prepend the DINING_OPTIONS_INSTRUCTION to the node_text
                    if node.metadata.get("isDiningOptions", False):
                        node_text = (
                            textwrap.indent(DINING_OPTIONS_INSTRUCTION, 2 * "\t")
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

        order = llm_call(
            system_prompt=EXTRACTOR_SYSTEM_PROMPT,
            prompt=EXTRACTOR_USER_PROMPT.format(
                context=context, chat_history=chat_history
            ),
            response_format=OrderInput,
            openai=True,
        )

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

        logger.debug(
            f"[ToastTool._finalize_order_details] Extracted structured data: {order}"
        )
        logger.debug(
            f"[ToastTool._finalize_order_details] Extracted structured data type: {type(order)}"
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
                f"Order #{order.guid} submitted successfully! "
                f"Your total is ${order.checks[0].totalAmount}. "
                f"Your order summary: {order.checks[0].selections}.\n\n"
                f"Your order will be ready for pickup at {order.estimatedFulfillmentDate}",
            )
        except Exception as e:
            logger.error(f"[ToastTool._submit_order] Failed to submit the order: {e}")
            return "There was an error while submitting the order. Please try again."

    def _get_order_prices(self, order: OrderInput) -> str:
        # Retrieve the bearer token
        toast_bearer_token = self._toast_bearer_token
        if not toast_bearer_token:
            return (
                "Failed to authenticate ordering tool. "
                "Please reach out to our support team at help@palona.ai "
                "for assistance."
            )
        try:
            order = get_order_prices(
                toast_bearer_token,
                self.store_id,
                order,
                general_api_endpoint=self.general_api_endpoint,
            )
            return Price(
                amount=order.checks[0].amount,
                taxAmount=order.checks[0].taxAmount,
                totalAmount=order.checks[0].totalAmount,
            ).model_dump_json()
        except Exception as e:
            logger.error(
                f"[ToastTool._get_order_prices] Failed to get the order prices: {e}"
            )
            return (
                "There was an error while getting the order prices. Please try again."
            )

    @tool
    def get_order_prices_tool(self) -> str:
        """
        Gets pricing information for the current order.

        Args:
            None

        Returns:
            str: JSON string containing order pricing details
        """
        try:
            order = self._construct_order()

            # If the order is a string, it indicates an error message
            # In this case, return the error message
            if isinstance(order, str):
                return order

            return self._get_order_prices(order)
        except Exception as e:
            logger.error(
                f"[ToastTool.get_order_prices_tool] Error in get order prices: {e}"
            )
            return (
                "There was an error while getting the order prices. Please try again."
            )

    def _create_payment_intent_for_order(
        self,
        order: OrderInput,
        external_reference_id: str | None = None,
        payments_api_endpoint: str | None = None,
    ) -> PaymentIntentResponse | str:
        """
        Creates a payment intent for an order.

        Args:
            order: The order to create a payment intent for
            external_reference_id: Optional unique identifier for this payment

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

            # Calculate total amount in cents
            total_amount_cents = int(order.checks[0].totalAmount * 100)  # type: ignore

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
                f"[ToastTool._create_payment_intent_for_order] Created payment intent: {payment_intent_response.id}"
            )

            return payment_intent_response

        except Exception as e:
            logger.error(
                f"[ToastTool._create_payment_intent_for_order] Error creating payment intent: {e}"
            )
            return "Failed to create payment intent. Please try again."

    def _generate_iframe_payment_link(
        self,
        email: str,
        store_id: str,
        order_external_id: str,
        payment_intent_external_reference_id: str,
        session_secret: str,
        subtotal_cents: int,
        tips_cents: int = 0,
        payment_api_endpoint: str = "https://ws-sandbox-api.eng.toasttab.com",
    ) -> str:
        """
        Generates a hosted payment iframe link for the given order and payment intent.

        Args:
            store_id (str): The store ID.
            order_external_id (str): The external ID of the order.
            payment_intent_external_reference_id (str): The external reference ID of the payment intent.
            session_secret (str): The session secret from the payment intent.
        Returns:
            str: The URL for the hosted payment iframe.
        """

        try:
            # Use sandbox API endpoints for iframe bearer token

            # Get iframe bearer token (for iframe initialization)
            # This uses TOAST_PAYMENT_IFRAME_CLIENT_CREDENTIALS
            try:
                iframe_bearer_token = get_toast_access_token_from_aws(
                    token_api_endpoint=payment_api_endpoint,
                    token_name="TOAST_PAYMENT_IFRAME_ACCESS_TOKEN",
                    credential_name="TOAST_PAYMENT_IFRAME_CLIENT_CREDENTIALS",
                )
            except ValueError as e:
                logger.error(
                    f"[ToastTool._generate_iframe_payment_link] Failed to get iframe bearer token: {e}"
                )
                return "Failed to authenticate for iframe. Please try again."

            if not iframe_bearer_token:
                logger.error(
                    "[ToastTool._generate_iframe_payment_link] Failed to get iframe bearer token"
                )
                return "Failed to get iframe bearer token. Please try again."

            logger.debug(
                "[ToastTool._generate_iframe_payment_link] Got iframe bearer token"
            )

            # Generate RSA private key for JWT
            private_key = rsa.generate_private_key(
                public_exponent=65537, key_size=2048, backend=default_backend()
            )

            # Create JWT payload with required claims
            payload = {
                "email": email,
                "storeId": store_id,
                "orderExternalId": order_external_id,
                "paymentIntentExternalReferenceId": payment_intent_external_reference_id,
                "subtotal": subtotal_cents,
                "tips": tips_cents,
                "sessionSecret": session_secret,
                "iframeBearerToken": iframe_bearer_token.access_token,
                "iat": int(time.time()),
                "exp": int(time.time()) + 15 * 60,  # Token valid for 15 minutes
            }

            # Sign JWT with RS256 algorithm
            token = jwt.encode(
                payload,
                private_key,
                algorithm="RS256",
            )

            # Remove any trailing dots from the token
            token = token.rstrip(".")

            # Construct the iframe URL
            iframe_url = f"{self.hosted_payment_iframe_endpoint}?t={token}"

            logger.debug(
                f"[ToastTool._generate_iframe_payment_link] Generated iframe URL: {iframe_url}"
            )

            return iframe_url

        except Exception as e:
            logger.error(
                f"[ToastTool._generate_iframe_payment_link] Error generating iframe payment link: {e}"
            )
            return "Failed to generate payment link. Please try again."
