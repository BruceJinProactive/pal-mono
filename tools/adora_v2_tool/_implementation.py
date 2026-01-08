import asyncio
import json
import threading

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import task, tool

from agent.tool import ToolMetadata
from agent.tool.internal.query_messages_tool import QueryMessagesTool
from tools.adora_v2_tool._apis import (
    api_check_store_ordering_status,
    api_get_store_info,
    api_process_order,
    api_validate_address,
    api_validate_coupon_code,
    api_validate_order,
    get_adora_pos_auth_token,
)
from tools.adora_v2_tool._llm_constants import EXTRACTOR_SYSTEM_PROMPT
from tools.adora_v2_tool._utils import (
    add_lat_long_to_address,
    build_context,
    build_process_order_request,
    build_validate_address_request,
    get_adora_credentials,
)
from tools.adora_v2_tool.classes import (
    BackdoorToolPrompt,
    BaseDeliveryAddress,
    ClientCustomerInfo,
    DeliveryAddress,
    OrderRequestBase,
    OrderType,
    PaymentType,
    ValidateOrderRequest,
)
from tools.utils.ordering._llm import async_llm_call
from tools.utils.ordering._query_engine import create_query_engine
from tools.utils.ordering._utils import get_relevant_docs_v2, is_valid_email
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

    @task(name="_get_bearer_token")
    async def _get_bearer_token(self) -> str | None:
        """Get cached bearer token or fetch new one if not cached."""
        logger.debug(
            f"[AdoraV2Tool._get_bearer_token] Thread: {threading.current_thread().name} (ID: {threading.current_thread().ident})"
        )

        async with self._token_lock:
            if self._cached_bearer_token:
                return self._cached_bearer_token

            api_key, api_secret = await get_adora_credentials(
                self.tool_metadata.account_name or "", self.store_id
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
    async def check_address(
        self, delivery_address: BaseDeliveryAddress
    ) -> tuple[str, dict | None]:
        """
        This tool can be used to validate whether or not an address is within a
        delivery zone. Call this tool whenever you need to confirm if a certain
        delivery address can be delivered to.

        Args:
            delivery_address (BaseDeliveryAddress): A structured delivery address containing:
                - address: Street address (e.g., "123 Main St") (required)
                - city: City name (e.g., "Springfield") (required)
                - state: Two-letter US state abbreviation (e.g., "IL") (required)
                - zip: ZIP code (e.g., "62704") (required)

        Returns:
            str: Validation result indicating if the address is within the delivery zone.
        """
        logger.debug(
            f"[AdoraV2Tool.check_address] Thread: {threading.current_thread().name} (ID: {threading.current_thread().ident}), address: {delivery_address}"
        )

        if missing := [
            f
            for f, v in [
                ("street number", delivery_address.street_number),
                ("street name", delivery_address.street_name),
                ("city", delivery_address.city),
                ("state", delivery_address.state),
                ("zip code", delivery_address.zip),
            ]
            if v == "N/A"
        ]:
            return f"Please provide the following: {', '.join(missing)}.", None

        bearer_token, geocoding_result = await asyncio.gather(
            self._get_bearer_token(),
            add_lat_long_to_address(delivery_address),
        )

        if not bearer_token:
            return "Failed to authenticate.", None

        if not geocoding_result:
            return (
                "The address provided is invalid. Please provide a valid address.",
                None,
            )

        validate_address_request = build_validate_address_request(
            self.store_id, geocoding_result, delivery_address
        )
        result = await api_validate_address(bearer_token, validate_address_request)

        # If validation failed, return error message
        if isinstance(result, str):
            return result, None

        return (
            f"Address is valid and within delivery zone. {result}",
            {"lat_lng": geocoding_result, "type_id": result.type_id},
        )

    @tool
    async def fulfill_order(
        self,
        customer_info: ClientCustomerInfo,
        order_type: OrderType,
        payment_type: PaymentType,
        order_items: list[str],
        delivery_address: BaseDeliveryAddress | None,
        promise_date_time: str | None = None,
        coupon_code: str | None = None,
    ) -> str:
        """
        Fulfills and submits customer order to the POS system and provides order confirmation.

        Use when ALL of the following conditions are met:
        - Customer has provided all required information (customer info, order items, delivery address if applicable)
        - Order items have been explicitly confirmed by the user
        - User explicitly expresses willingness to checkout (e.g., "checkout", "place order", "complete order", "I'm ready to order")

        DO NOT use if:
        - Customer has not explicitly said they want to checkout/place order/complete order
        - Customer is still browsing, asking questions, or modifying their order
        - Any required information is missing or unconfirmed

        Args:
            customer_info (ClientCustomerInfo): Customer information containing:
                - name: Customer first name (required)
                - lastname: Customer last name (default: "via Palona")
                - phone: Customer phone number in format (123) 456-7890 (required)
                - email: Customer email address (optional)
            order_type (OrderType): Type of order. Options: "TakeOut", "Delivery"
            payment_type (PaymentType): Payment type. Options: "PayInStore", "PaymentLink".
                IMPORTANT: Always use "PaymentLink" for both pick up and delivery orders if payment type is not mentioned
                - Delivery orders must always use "PaymentLink"
            order_items (list[str]): List of order item names without modifiers.
                Extract complete dish or drink names without size or quantity.
                Examples: ["Margherita Pizza", "Caesar Salad", "Coca Cola"]
            delivery_address (BaseDeliveryAddress | None): Delivery address for delivery orders.
                Required fields:
                - street_number: Street number (required). Remove spaces in street numbers (e.g., "12 34" → "1234")
                - street_name: Street name (required)
                - extended_address: Unit/apartment (empty string if not provided)
                - city: City name (required)
                - state: Two-letter US state abbreviation (required, e.g., "TX" not "Texas")
                - zip: ZIP code (required)
                Address extraction rules:
                - Use only 2-letter state abbreviations, convert full names to abbreviations
                - Remove all spaces within street numbers from voice recognition errors
                - Set missing fields to "N/A"
                Set to None for pickup/dine-in orders.
            promise_date_time (str | None): Scheduled order date/time in ISO 8601 format (YYYY-MM-DDTHH:MM:SS).
                - Set to None for ASAP orders or when timing not specified (DEFAULT)
                - ONLY set when customer explicitly requests future time
                - Examples: "2025-01-15T14:30:00", "2025-12-25T12:00:00"
                - Must be in store's local timezone
            coupon_code (str | None): Coupon code to apply to the order (optional).
                - Set to None if no coupon mentioned
                - If provided, will be validated before processing order
                - Invalid coupons will result in order rejection with error message

        Returns:
            str: Order confirmation with order ID and final total.
        """

        logger.debug(f"[AdoraV2Tool.fulfill_order] Order items: {order_items}")

        # Annotate input data for Datadog tracing
        LLMObs.annotate(
            input_data={
                "order_type": order_type.value,
                "payment_type": payment_type.value,
                "order_items": order_items,
                "has_delivery_address": delivery_address is not None,
                "customer_name": customer_info.name,
            }
        )

        # Gather common tasks
        with LLMObs.task(name="fulfill_order.gather_context"):
            bearer_token, chat_history, item_context = await asyncio.gather(
                self._get_bearer_token(),
                asyncio.to_thread(self.query_messages_tool.query_messages),
                get_relevant_docs_v2(order_items, self.query_engine),
            )

        if not bearer_token:
            return "Failed to authenticate with Adora API."

        # Validate coupon code if provided
        coupon_id = None
        if coupon_code:
            with LLMObs.task(name="fulfill_order.validate_coupon"):
                # Annotate input
                LLMObs.annotate(
                    metadata={
                        "coupon_code": coupon_code,
                    }
                )

                coupon_result = await api_validate_coupon_code(
                    bearer_token, self.store_id, coupon_code
                )

                # Annotate output
                if coupon_result:
                    LLMObs.annotate(
                        metadata={
                            "is_valid": coupon_result.is_valid,
                            "coupon_id": coupon_result.coupon_id,
                            "message": coupon_result.message,
                        }
                    )
                else:
                    LLMObs.annotate(
                        metadata={
                            "is_valid": False,
                            "error": "API call failed",
                        }
                    )

                if not coupon_result or not coupon_result.is_valid:
                    error_message = (
                        coupon_result.message
                        if coupon_result and coupon_result.message
                        else "Coupon code validation failed"
                    )
                    return f"Invalid coupon code '{coupon_code}'. {error_message}. Please provide a valid coupon code or proceed without a coupon."

                coupon_id = coupon_result.coupon_id
                logger.info(
                    f"[AdoraV2Tool.fulfill_order] Validated coupon code '{coupon_code}', ID: {coupon_id}"
                )

        # Apply backdoor overrides if present
        system_prompt = (
            self.backdoor_tool_prompt.get(
                BackdoorToolPrompt.SYSTEM_PROMPT, EXTRACTOR_SYSTEM_PROMPT
            )
            if self.backdoor_tool_prompt
            else EXTRACTOR_SYSTEM_PROMPT
        )

        # Build complete context
        context, context_template = build_context(
            order_items, item_context, self.tool_metadata.timezone
        )
        if self.backdoor_tool_prompt:
            context_template = self.backdoor_tool_prompt.get(
                BackdoorToolPrompt.USER_PROMPT, context_template
            )

        # LLM call to extract order items with modifiers/sizes/quantities
        with LLMObs.task(name="fulfill_order.extract_order_details"):
            formatted_prompt = context_template.format(
                context=context, chat_history=chat_history
            )

            # Annotate input before LLM call
            LLMObs.annotate(
                metadata={
                    "llm_input_system_prompt": system_prompt,
                    "llm_input_prompt": formatted_prompt,
                }
            )

            order_request_base = await async_llm_call(
                system_prompt=system_prompt,
                prompt=formatted_prompt,
                response_format=OrderRequestBase,
                name=self.fulfill_order.__name__,
                openai=True,
            )

            # Annotate output after LLM call
            if order_request_base and hasattr(order_request_base, "model_dump"):
                llm_output_data = order_request_base.model_dump()
            else:
                llm_output_data = (
                    str(order_request_base) if order_request_base else "None"
                )
            LLMObs.annotate(
                metadata={
                    "llm_output": llm_output_data,
                    "output_type": str(type(order_request_base)),
                }
            )

        # Validate and parse LLM response
        if not isinstance(order_request_base, OrderRequestBase):
            # Fallback: If response is a JSON string, try to parse it
            if isinstance(order_request_base, str):
                try:
                    logger.info(
                        "[AdoraV2Tool.fulfill_order] Attempting to parse JSON string response"
                    )
                    order_dict = json.loads(order_request_base)
                    order_request_base = OrderRequestBase(**order_dict)
                    logger.info(
                        "[AdoraV2Tool.fulfill_order] Successfully parsed JSON string to OrderRequestBase"
                    )
                except (json.JSONDecodeError, ValueError) as e:
                    logger.error(
                        f"[AdoraV2Tool.fulfill_order] Parse failed: Extracted Order: {order_request_base}; Type: {type(order_request_base)}; Error: {e}"
                    )
                    return "Failed to extract order information. Please provide all order details and try again."
            else:
                logger.error(
                    f"[AdoraV2Tool.fulfill_order] Parse failed: Extracted Order: {order_request_base}; Type: {type(order_request_base)}"
                )
                return "Failed to extract order information. Please provide all order details and try again."

        # Convert to ValidateOrderRequest with provided fields and extracted items
        order_request = ValidateOrderRequest(
            storeId=self.store_id,
            OrderType=order_type,
            paymentType=payment_type,
            promiseDateTime=promise_date_time,
            customer=customer_info,
            items=order_request_base.items,
            orderComment=order_request_base.order_comment,
            couponIds=[coupon_id] if coupon_id else None,
        )

        # Set email to default if empty or invalid
        if not order_request.customer.email or not is_valid_email(
            order_request.customer.email
        ):
            order_request.customer.email = "orderingagent@palona.ai"

        # Handle delivery orders
        if order_request.order_type == OrderType.DELIVERY:
            if not delivery_address:
                return "This is a delivery order. Please provide your delivery address so it can be validated before placing the order."

            with LLMObs.task(name="fulfill_order.validate_delivery_address"):
                # Annotate input before API call
                LLMObs.annotate(
                    metadata={
                        "input_address": delivery_address.model_dump(),
                    }
                )

                validate_address_result = await self.check_address(delivery_address)  # type: ignore
                address_data = validate_address_result[1]

                # Annotate output after API call
                LLMObs.annotate(
                    metadata={
                        "validation_success": address_data is not None,
                        "validated_lat_lng": (
                            address_data["lat_lng"] if address_data else None
                        ),
                        "address_type_id": (
                            address_data["type_id"] if address_data else None
                        ),
                    }
                )

                if not address_data:
                    return validate_address_result[0]

                order_request.delivery_address = DeliveryAddress(
                    **delivery_address.model_dump(),
                    lat=address_data["lat_lng"][0],  # type: ignore
                    lng=address_data["lat_lng"][1],  # type: ignore
                    type_id=address_data["type_id"],  # type: ignore
                )
                order_request.payment_type = PaymentType.PAYMENT_LINK

        logger.debug(
            f"[AdoraV2Tool.fulfill_order] Final order request: {order_request.model_dump()}"
        )

        # Step 1: Validate the order
        with LLMObs.task(name="fulfill_order.validate_order"):
            # Annotate input before API call
            LLMObs.annotate(
                metadata={
                    "api_input": order_request.model_dump(),
                }
            )

            validate_result = await api_validate_order(bearer_token, order_request)
            logger.debug(
                f"[AdoraV2Tool.fulfill_order] validate_result: {validate_result}"
            )

            # Annotate output after API call
            if isinstance(validate_result, str):
                api_response_data = validate_result
                validation_success = False
                order_key = None
                subtotal = None
                total = None
                delivery_charge = None
            else:
                api_response_data = (
                    validate_result.model_dump()
                    if hasattr(validate_result, "model_dump")
                    else str(validate_result)
                )
                validation_success = bool(getattr(validate_result, "key", None))
                order_key = getattr(validate_result, "key", None)
                subtotal = getattr(validate_result, "sub_total", None)
                total = getattr(validate_result, "total", None)
                delivery_charge = getattr(validate_result, "delivery_charge", None)

            LLMObs.annotate(
                metadata={
                    "api_response": api_response_data,
                    "validation_success": validation_success,
                    "order_key": order_key,
                    "subtotal": subtotal,
                    "total": total,
                    "delivery_charge": delivery_charge,
                }
            )

            if isinstance(validate_result, str) or not validate_result.key:
                return f"Validation failed: {validate_result if isinstance(validate_result, str) else 'No order key returned'}"

        # Step 2: Build process order request and process the order
        with LLMObs.task(name="fulfill_order.process_order"):
            process_order_request = build_process_order_request(
                order_request, validate_result
            )

            # Annotate input before API call
            LLMObs.annotate(
                metadata={
                    "api_input": process_order_request.model_dump(),
                }
            )

            process_result = await api_process_order(
                bearer_token, process_order_request
            )
            logger.debug(
                f"[AdoraV2Tool.fulfill_order] process_result: {process_result}"
            )

            # Annotate output after API call
            if isinstance(process_result, str):
                api_response_data = process_result
            elif hasattr(process_result, "model_dump"):
                api_response_data = process_result.model_dump()
            else:
                api_response_data = str(process_result)
            LLMObs.annotate(
                metadata={
                    "api_response": api_response_data,
                }
            )

            if isinstance(process_result, str):
                return f"Processing failed: {process_result}"

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

        # Use payment URL from process result
        payment_url = process_result.payment_url
        if payment_url:
            confirmation += f"\nPayment URL: {payment_url}"

        # Annotate final output for Datadog tracing
        LLMObs.annotate(
            output_data=confirmation,
            metadata={
                "order_id": process_result.order_id,
                "order_number": process_result.order_no,
                "total_amount": validate_result.total,
                "payment_url_provided": payment_url is not None,
            },
        )

        return confirmation
