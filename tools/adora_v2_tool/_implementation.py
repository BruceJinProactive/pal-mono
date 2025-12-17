import asyncio
import threading

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs.decorators import tool

from agent.tool import ToolMetadata
from agent.tool.internal.query_messages_tool import QueryMessagesTool
from tools.adora_v2_tool._apis import (
    api_check_store_ordering_status,
    api_get_store_info,
    api_process_order,
    api_validate_address,
    api_validate_order,
    get_adora_pos_auth_token,
)
from tools.adora_v2_tool._utils import (
    add_lat_long_to_address,
    build_context,
    build_extraction_prompt,
    extract_street_parts,
    get_adora_credentials,
)
from tools.adora_v2_tool.classes import (
    BackdoorToolPrompt,
    DeliveryAddress,
    OrderType,
    PaymentType,
    ValidateOrderRequest,
)
from tools.utils.ordering._llm import async_llm_call
from tools.utils.ordering._query_engine import create_query_engine
from tools.utils.ordering._utils import get_relevant_docs, is_valid_email
from tools.utils.ordering.classes import SubQueries
from utils.log import logger


class AdoraV2Tool(Toolkit):
    def __init__(
        self,
        store_id: str,
        namespace: str,
        tool_metadata: ToolMetadata,
        backdoor_tool_prompt: dict | None = None,
        **kwargs,
    ):
        super().__init__(name="adora_v2_tool")

        # Store configuration
        self.store_id = store_id
        self.namespace = namespace
        self.tool_metadata = tool_metadata
        self.backdoor_tool_prompt = backdoor_tool_prompt or {}

        # Cache for bearer token with async lock
        self._cached_bearer_token: str | None = None
        self._token_lock = asyncio.Lock()

        # Cache for most recently validated delivery address
        # Security note: This cache is instance-scoped (per-request) and not shared across conversations
        self._cached_delivery_address: DeliveryAddress | None = None
        self._address_lock = asyncio.Lock()

        # Log instance creation with built-in id
        instance_id = id(self)
        logger.debug(f"[AdoraV2Tool] Tool instance created: id={instance_id}")

        # Create query engine and query messages tool
        self.query_engine = create_query_engine(self.namespace, "agents")
        self.query_messages_tool = QueryMessagesTool(self.tool_metadata)

        # Register tools
        self.register(self.check_store_ordering_status)
        self.register(self.get_store_info)
        self.register(self.check_address)
        self.register(self.fulfill_order)

    async def _get_bearer_token(self) -> str | None:
        """Get cached bearer token or fetch new one if not cached."""
        logger.debug(
            f"[AdoraV2Tool._get_bearer_token] Thread: {threading.current_thread().name} (ID: {threading.current_thread().ident})"
        )

        async with self._token_lock:
            if self._cached_bearer_token:
                return self._cached_bearer_token

            api_key, api_secret = await get_adora_credentials(
                self.tool_metadata.account_name or ""
            )
            if not api_key or not api_secret:
                logger.error("[AdoraV2Tool] Failed to retrieve Adora credentials")
                return None

            token = await get_adora_pos_auth_token(api_key, api_secret, self.store_id)
            if not token:
                logger.error(
                    "[AdoraV2Tool] Failed to retrieve bearer token from Adora API"
                )
                return None

            self._cached_bearer_token = token
            return self._cached_bearer_token

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
            f"[AdoraV2Tool.get_store_info] Thread: {threading.current_thread().name} (ID: {threading.current_thread().ident}), date: {date}"
        )

        bearer_token = await self._get_bearer_token()
        if not bearer_token:
            return "Failed to authenticate with Adora API."

        store_info_response = await api_get_store_info(
            bearer_token, self.store_id, date
        )
        if not store_info_response:
            return "Failed to retrieve store information."

        return str(store_info_response)

    @tool
    async def check_store_ordering_status(self) -> str:
        """
        Check the online ordering status of the store.

        Returns:
            str: The online ordering status of the store.
        """
        logger.debug(
            f"[AdoraV2Tool.check_store_ordering_status] Thread: {threading.current_thread().name} (ID: {threading.current_thread().ident})"
        )

        bearer_token = await self._get_bearer_token()
        if not bearer_token:
            return "Failed to authenticate with Adora API."

        status_response = await api_check_store_ordering_status(
            bearer_token, self.store_id
        )
        if not status_response:
            return "Failed to retrieve store status."

        is_online = status_response.get("isOnline", False)
        return f"Store online ordering status: {'Online' if is_online else 'Offline'}"

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
            f"[AdoraV2Tool.check_address] Thread: {threading.current_thread().name} (ID: {threading.current_thread().ident}), address: {address}"
        )

        # Use async_llm_call to extract address into DeliveryAddress format
        delivery_address = await async_llm_call(
            system_prompt="Extract the address into the given output format.",
            prompt=address,
            response_format=DeliveryAddress,
            openai=False,
        )

        if not isinstance(delivery_address, DeliveryAddress):
            return "Failed to identify address. Please try again by providing the full address."

        if missing := [
            f
            for f, v in [
                ("street address", delivery_address.address),
                ("city", delivery_address.city),
                ("state", delivery_address.state),
                ("zip code", delivery_address.zip),
            ]
            if v == "N/A"
        ]:
            return f"Please provide the following: {', '.join(missing)}."

        bearer_token, geocoding_result = await asyncio.gather(
            self._get_bearer_token(),
            add_lat_long_to_address(delivery_address),
        )

        if not bearer_token:
            return "Failed to authenticate."

        geocoding_success, geocoding_error = geocoding_result
        if not geocoding_success:
            return geocoding_error

        street_no, street_name = extract_street_parts(delivery_address.address)

        result = await api_validate_address(
            bearer_token,
            self.store_id,
            delivery_address,
            street_no,
            street_name,
        )

        # If validation failed, return error message
        if isinstance(result, str):
            return result

        # Address is valid - cache it for use in fulfill_order (always refresh cache)
        async with self._address_lock:
            self._cached_delivery_address = delivery_address
            logger.debug(
                f"[AdoraV2Tool.check_address] Cached validated delivery address: {delivery_address}"
            )

        return f"Address is valid and within delivery zone. {result}"

    @tool
    async def fulfill_order(self, order_items: list[str]) -> str:
        """
        Fulfills customer order by validating and processing it, returning confirmation.
        This submits the order to the POS system and provides order confirmation.

        Use when customer is ready to place/complete their order.
        Use when customer says "checkout", "place order", "complete order", etc.

        Args:
            order_items (list[str]): List of order items extracted from chat history.
                Requirements:
                - Extract the **complete dish or drink name**, but **remove size or quantity information**.
                - Do not shorten or generalize the dish.
                - Only include items that the user **explicitly confirmed or finalized** as part of their order.
                - Output a JSON array of strings with **cleaned item names**.

        Returns:
            str: Order confirmation with order ID and final total.
        """

        logger.debug(f"[AdoraV2Tool.fulfill_order] Order items: {order_items}")
        bearer_token, chat_history_result = await asyncio.gather(
            self._get_bearer_token(),
            asyncio.to_thread(self.query_messages_tool.query_messages),
        )

        if not bearer_token:
            return "Failed to authenticate with Adora API."

        chat_history: str = str(chat_history_result)  # type: ignore

        # Build default prompts
        system_prompt = build_extraction_prompt(
            ValidateOrderRequest, self.fulfill_order.__name__
        )

        # Apply backdoor overrides if present
        system_prompt = self.backdoor_tool_prompt.get(
            BackdoorToolPrompt.SYSTEM_PROMPT, system_prompt
        )

        # Get menu context and build complete context
        item_context = await asyncio.to_thread(
            get_relevant_docs,
            self.query_engine,
            chat_history,
            ", ".join(order_items),
            SubQueries,
        )
        context, context_template = build_context(
            item_context, self.tool_metadata.timezone
        )
        if self.backdoor_tool_prompt:
            context_template = self.backdoor_tool_prompt.get(
                BackdoorToolPrompt.USER_PROMPT, context_template
            )

        order_request = await async_llm_call(
            system_prompt=system_prompt,
            prompt=context_template.format(context=context, chat_history=chat_history),
            response_format=ValidateOrderRequest,
            name=self.fulfill_order.__name__,
            openai=False,
        )

        if not isinstance(order_request, ValidateOrderRequest):
            return (
                "Failed to extract order information. Please provide all order details."
            )

        order_request.store_id = self.store_id

        # Set email to default if empty or invalid
        email = order_request.customer.email
        if not email or not is_valid_email(email):
            order_request.customer.email = "orderingagent@palona.ai"

        # Handle delivery address for delivery orders
        if order_request.order_type == OrderType.DELIVERY:
            async with self._address_lock:
                if not self._cached_delivery_address:
                    return "This is a delivery order. Please provide your delivery address so it can be validated before placing the order."

                logger.info(
                    f"[AdoraV2Tool.fulfill_order] Using cached delivery address: {self._cached_delivery_address}"
                )
                order_request.delivery_address = self._cached_delivery_address
                order_request.payment_type = PaymentType.PAYMENT_LINK

        # Step 1: Validate the order
        validate_result = await api_validate_order(bearer_token, order_request)
        logger.debug(f"[AdoraV2Tool.fulfill_order] validate_result: {validate_result}")
        if isinstance(validate_result, str) or not validate_result.key:
            return f"Validation failed: {validate_result if isinstance(validate_result, str) else 'No order key returned'}"

        # Step 2: Process the order
        process_result = await api_process_order(
            bearer_token, order_request, validate_result
        )
        logger.debug(f"[AdoraV2Tool.fulfill_order] process_result: {process_result}")
        if isinstance(process_result, str):
            return f"Processing failed: {process_result}"

        # Step 3: Return confirmation
        if not process_result.success:
            return f"Order processing failed: {process_result}"

        confirmation = (
            f"Order successfully placed!\n"
            f"Order ID: {process_result.order_id}\n"
            f"Order Number: {process_result.order_no}\n"
            f"Subtotal: ${validate_result.sub_total:.2f}\n"
            f"Tax: ${validate_result.tax_amount:.2f}\n"
            f"Service Charge: ${validate_result.service_charge:.2f}\n"
            f"Delivery Charge: ${validate_result.delivery_charge:.2f}\n"
            f"Total: ${validate_result.total:.2f}\n"
        )

        # Use payment URL from process result first, fallback to validate result
        payment_url = process_result.payment_url or validate_result.payment_url
        if payment_url:
            confirmation += f"\nPayment URL: {payment_url}"

        return confirmation
