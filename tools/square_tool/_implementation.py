import json
import re
import uuid
from datetime import datetime
from decimal import Decimal
from functools import cached_property
from typing import Optional
from zoneinfo import ZoneInfo

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import tool
from pydantic import ValidationError

import db
from agent.tool import ToolMetadata
from agent.tool.internal.query_messages_tool import QueryMessagesTool
from db.tables.types import IntegrationProvider, IntegrationType
from services import integration_service
from services.transaction_service import save_order
from tools.square_tool._apis import create_payment_link
from tools.square_tool._prompt_constants import (
    RETRIEVE_ORDER_ITEMS_SYSTEM_PROMPT,
    SQUARE_EXTRACTOR_SYSTEM_PROMPT,
    SQUARE_EXTRACTOR_USER_PROMPT,
)
from tools.square_tool._utils import (
    create_comprehensive_menu,
    create_square_order_with_modifiers,
    format_order_success_message,
)
from tools.square_tool.classes import (
    CheckoutOptions,
    CreatePaymentLinkInput,
    ExtractedOrderWithModifiers,
    Order,
    PaymentLink,
    SquareAccessToken,
)
from tools.utils.ordering._llm import llm_call
from tools.utils.ordering._query_engine import create_query_engine
from tools.utils.ordering._utils import get_chat_history, get_relevant_docs
from tools.utils.ordering.classes import SubQueries
from utils.log import logger


class SquareTool(Toolkit):
    """
    Main Square Tool implementation for POS, payments, and catalog operations.

    This tool has been refactored to use Pinecone knowledge base for menu item retrieval
    and ID mapping instead of the hardcoded MENU_ID dictionary. The new approach:

    1. Uses Pinecone vector search to find relevant catalog documents based on chat history
    2. Extracts item_id, variation_id, and modifier_id directly from the catalog documents
    3. Creates orders using the extracted IDs without relying on MENU_ID

    Constructor Parameters:
        access_token (str, optional): Square API access token (fallback if integration not found)
        location_id (str): Square location ID
        namespace (str): Pinecone namespace containing the catalog documents
        index_name (str): Pinecone index name
        tool_metadata (ToolMetadata): Tool metadata for chat history access (includes project_id)
        use_production (bool): Whether to use production Square API

    Expected Pinecone Document Format:
        # Item Name (item_id: ITEM_ID_HERE)
        **Variation ID:** VARIATION_ID_HERE

        ## Modifiers
          ### Category Name
          - Modifier Name (modifier_id: MODIFIER_ID_HERE)
    """

    def __init__(
        self,
        location_id: str,
        namespace: str,
        index_name: str,
        tool_metadata: ToolMetadata,
        access_token: Optional[str] = None,
        use_production: bool = False,
        backdoor_tool_prompt: dict | None = None,
    ):
        super().__init__(name="square_tool")

        self.tool_metadata = tool_metadata
        self.use_production = use_production
        self.location_id = location_id
        self.fallback_access_token = access_token
        self.namespace = namespace
        self.index_name = index_name
        self.backdoor_tool_prompt = backdoor_tool_prompt or {}

        # Initialize query messages tool
        self.query_messages_tool = QueryMessagesTool(self.tool_metadata)

        # Initialize Pinecone query engine for catalog retrieval
        self.query_engine = create_query_engine(
            namespace=self.namespace, index_name=self.index_name
        )

        # Register tools
        self.register(self.create_order_and_payment_link)

    def _save_order_to_db(
        self,
        created_order: Order,
        matched_items: list[dict],
        payment_url: Optional[str] = None,
    ) -> None:
        """
        Save Square transaction information to `transactions` table only.

        Args:
            created_order: The Square order object returned by API
            matched_items: Line items used to construct the order
            payment_url: Optional payment link to store as tracking link
        """
        try:
            subtotal_decimal = None
            total_money = getattr(created_order, "total_money", None)

            amount_cents = getattr(total_money, "amount", None) if total_money else None
            if amount_cents is not None:
                subtotal_decimal = Decimal(amount_cents) / Decimal("100")
            transaction_id = save_order(
                tool_metadata=self.tool_metadata,
                vendor=IntegrationProvider.square,
                order_id=created_order.id or "",
                store_id=self.location_id,
                status="pending",
                fulfillment_strategy="pickup",
                subtotal=subtotal_decimal,
                order_items=matched_items or None,
                order_time=datetime.now(),
                tracking_link=payment_url,
                session=None,
            )
            if transaction_id:
                logger.debug(
                    f"[SquareTool._save_order_to_db] Saved transaction to database: {transaction_id}"
                )
        except Exception as transaction_error:
            logger.warning(
                f"[SquareTool._save_order_to_db] Failed to save transaction data: {transaction_error}",
                exc_info=True,
            )

    def _get_access_token_from_integration(self) -> Optional[str]:
        """
        Retrieve Square access token from integration service.

        Returns:
            Optional[str]: Access token if integration found and has token, None otherwise
        """
        project_id = self.tool_metadata.project_id
        if not project_id:
            logger.debug("No project_id in metadata, cannot retrieve integration")
            return None

        try:
            # Create a database session to query integrations
            session = next(db.get_db())
            try:
                integration = integration_service.get_integration_by_project_and_type(
                    session=session,
                    account_id=self.tool_metadata.account_id,
                    project_id=project_id,
                    integration_type=IntegrationType.pos,
                )

                if integration and integration.access_token:
                    logger.debug("Retrieved access token from integration service")
                    return integration.access_token
                else:
                    logger.debug("No integration found or missing access token")
                    return None
            finally:
                session.close()

        except Exception as e:
            logger.warning(f"Failed to retrieve integration: {e}")
            return None

    @cached_property
    def _square_token(self) -> SquareAccessToken:
        """
        Returns the Square API access token, first trying integration service,
        then falling back to the token provided during initialization.

        Returns:
            SquareAccessToken: An object containing the access token for Square API calls.
        """
        with LLMObs.task(name="get_square_token"):
            # Try to get access token from integration service first
            access_token = self._get_access_token_from_integration()

            # Fallback to initializer token if no integration token found
            if not access_token:
                access_token = self.fallback_access_token
                if access_token:
                    logger.debug("Using fallback access token from initializer")
                else:
                    logger.error(
                        "No access token available from integration or fallback"
                    )
                    raise ValueError(
                        "No access token available from integration or fallback"
                    )
            bearer_token = SquareAccessToken(
                access_token=access_token,
                token_type="Bearer",
            )
            return bearer_token

    def _get_menu_info(self) -> str:
        """Get customer menu information for extraction prompt."""
        try:
            # Use the comprehensive menu for extraction context
            return create_comprehensive_menu(
                access_token=self._square_token,
                location_id=self.location_id,
                use_production=self.use_production,
                display_id=False,  # Don't show IDs in extraction context
            )

        except Exception as e:
            logger.error(f"[SquareTool._get_menu_info] Error: {e}")
            return "Menu information not available"

    def _create_payment_link(
        self, order: Order, total_item_count: int
    ) -> Optional[PaymentLink]:
        """Create payment link using the actual order and return URL."""
        try:
            payment_link_response = create_payment_link(
                self._square_token,
                CreatePaymentLinkInput(  # type: ignore
                    idempotency_key=str(uuid.uuid4()),
                    description=f"Order payment for {total_item_count} items",
                    order=order,  # Use the actual order object
                    checkout_options=CheckoutOptions(  # type: ignore
                        allow_tipping=False,
                        ask_for_shipping_address=False,
                        enable_coupon=False,
                        enable_loyalty=False,
                    ),
                    payment_note="Palona AI - Square order payment",
                    use_production=self.use_production,
                ),
            )

            if payment_link_response.errors:
                logger.error(
                    f"[SquareTool._create_payment_link] Errors: {payment_link_response.errors}"
                )
                return None

            if not payment_link_response.payment_link:
                logger.error(
                    "[SquareTool._create_payment_link] No payment link returned"
                )
                return None

            return payment_link_response.payment_link
        except Exception as e:
            logger.error(f"[SquareTool._create_payment_link] Error: {e}")
            return None

    def _construct_order(
        self, provided_chat_history: Optional[str] = None
    ) -> ExtractedOrderWithModifiers | str:
        """
        Construct order from chat history using Pinecone retrieval and LLM extraction.

        Args:
            provided_chat_history (Optional[str]): Optional pre-provided chat history to use instead of fetching.

        Returns:
            ExtractedOrderWithModifiers | str: Extracted order or error message.
        """
        # Use provided chat history or get it from the standardized functions

        chat_history = get_chat_history(self.query_messages_tool)

        context = get_relevant_docs(
            self.query_engine,
            chat_history,
            self.backdoor_tool_prompt.get(
                "order_item_prompt", RETRIEVE_ORDER_ITEMS_SYSTEM_PROMPT
            ),
            SubQueries,
        )

        # Get current date and time in the store's timezone
        store_tz = self.tool_metadata.timezone or "America/Los_Angeles"
        current_dt_store = datetime.now(ZoneInfo(store_tz))

        # Add current date/time to context for LLM to understand temporal references
        current_time_info = (
            f"\n\n<current_datetime>\n"
            f"Current date and time: {current_dt_store.strftime('%A, %B %d, %Y at %I:%M %p')} ({store_tz})\n"
            f"Timezone: {store_tz}\n"
            f"Use this timezone when formatting pickup_time in RFC 3339 format\n"
            f"</current_datetime>"
        )
        context += current_time_info  # type: ignore

        # Get prompt overrides or defaults
        system_prompt = self.backdoor_tool_prompt.get(
            "system_prompt", SQUARE_EXTRACTOR_SYSTEM_PROMPT
        )
        user_prompt_template = self.backdoor_tool_prompt.get(
            "user_prompt", SQUARE_EXTRACTOR_USER_PROMPT
        )

        order = llm_call(
            system_prompt=system_prompt,
            prompt=user_prompt_template.format(
                context=context, chat_history=chat_history
            ),
            response_format=ExtractedOrderWithModifiers,
            openai=False,
        )

        # Check if the order is a string and convert it to an ExtractedOrderWithModifiers object
        try:
            if order is None:
                raise ValueError("Order is None")

            if type(order) is str:
                order = json.loads(order)
                order = ExtractedOrderWithModifiers(**order)

            if not isinstance(order, ExtractedOrderWithModifiers):
                raise ValueError(
                    f"`order` object in type {type(order)} but expected type ExtractedOrderWithModifiers.\n"
                    f"`order` object: {order}"
                )

            # Validate RFC 3339 format for scheduled orders
            if order.schedule_type == "SCHEDULED":
                if not order.pickup_time:
                    return "Scheduled order requires a pickup/delivery time. Please specify when you want to pick up or have the order delivered (e.g., '2pm today', 'tomorrow at 5:30pm')."
                rfc3339_pattern = (
                    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}([+-]\d{2}:\d{2}|Z)$"
                )
                if not re.match(rfc3339_pattern, order.pickup_time):
                    return f"Invalid time format for scheduled order. Expected RFC 3339 format (e.g., '2025-01-26T14:00:00-08:00'), but got: '{order.pickup_time}'."

            logger.debug(f"Constructed order: {order}")
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

    def _validate_extracted_order(
        self, extracted_order: ExtractedOrderWithModifiers
    ) -> tuple[bool, str, list[dict]]:
        """
        Validate the extracted order and convert to the format needed for order creation.

        Args:
            extracted_order: The extracted order with items, IDs, and modifiers.

        Returns:
            tuple: (is_valid, error_message, converted_items)
        """
        if not extracted_order.items:
            return False, "No items found in the extracted order.", []

        converted_items = []
        missing_ids = []

        for item in extracted_order.items:
            # Check for required IDs
            if not item.item_id:
                missing_ids.append(f"{item.item_name}: missing item_id")
                continue
            if not item.variation_id:
                missing_ids.append(f"{item.item_name}: missing variation_id")
                continue

            # Process modifiers and validate their IDs
            processed_modifiers = []
            for modifier in item.modifiers:
                if not modifier.modifier_id:
                    logger.warning(
                        f"[SquareTool._validate_extracted_order] Missing modifier_id for modifier '{modifier.modifier_name}' "
                        f"in item '{item.item_name}' - skipping this modifier"
                    )
                    continue

                processed_modifiers.append(
                    {
                        "modifier_name": modifier.modifier_name,
                        "modifier_id": modifier.modifier_id,
                    }
                )

            # Convert to the format expected by create_square_order_with_modifiers
            item_dict = {
                "item_name": item.item_name,
                "item_id": item.item_id,
                "variation_id": item.variation_id,
                "quantity": item.quantity,
                "modifiers": processed_modifiers,
                "special_notes": item.special_notes,
            }
            converted_items.append(item_dict)

            logger.debug(
                f"[SquareTool._validate_extracted_order] Validated '{item.item_name}' "
                f"(item_id: {item.item_id}, variation_id: {item.variation_id}) "
                f"with {len(processed_modifiers)} valid modifiers"
            )

        if missing_ids:
            error_msg = "Missing required IDs for some items:\n" + "\n".join(
                missing_ids
            )
            return False, error_msg, []

        if not converted_items:
            return False, "No valid items found after validation.", []

        return True, "", converted_items

    def list_catalog_customer_menu(self, display_id: bool = False) -> str:
        """
        Get a customer-friendly menu from Square catalog.

        Use this tool to show customers available menu items, prices, and dietary information.

        Args:
            display_id: Whether to display item and modifier IDs (default: False)

        Returns:
            str: Customer-friendly food catalog information
        """
        try:
            # Use the comprehensive menu creation utility function
            return create_comprehensive_menu(
                access_token=self._square_token,
                location_id=self.location_id,
                use_production=self.use_production,
                display_id=display_id,
            )

        except Exception as e:
            logger.error(
                f"[SquareTool.list_catalog_customer_menu] Error getting menu: {e}"
            )
            return "Failed to get the menu, please try again."

    @tool
    def create_order_and_payment_link(self) -> str:
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

        Returns:
            str: Payment link URL and order details, or error message
        """
        try:
            # Check if we have query messages tool
            if not self.query_messages_tool:
                return (
                    "Chat history access not available. Please provide tool metadata."
                )

            # Step 1: Extract items with modifiers from chat history using Pinecone retrieval
            logger.debug(
                "[SquareTool] Step 1: Extracting items with modifiers from chat history using Pinecone retrieval"
            )
            extracted_order = self._construct_order()

            if isinstance(extracted_order, str):
                return extracted_order  # Return error message

            if not extracted_order.items:
                return "No food items found in the conversation history."

            logger.debug(
                f"[SquareTool] Found {len(extracted_order.items)} items to order"
            )

            # Step 2: Validate extracted order
            logger.debug("[SquareTool] Step 2: Validating extracted order")
            is_valid, error_message, converted_items = self._validate_extracted_order(
                extracted_order
            )

            if not is_valid:
                return error_message

            # Step 3: Create order with modifiers
            logger.debug("[SquareTool] Step 3: Creating Square order with modifiers")

            # Get customer name and phone number
            customer_name = extracted_order.customer_name
            phone_number = extracted_order.phone_number

            # Get fulfillment details
            fulfillment_type = extracted_order.fulfillment_type or "pickup"
            schedule_type = extracted_order.schedule_type or "ASAP"
            pickup_time = extracted_order.pickup_time
            prep_time_duration = extracted_order.prep_time_duration

            created_order = create_square_order_with_modifiers(
                self._square_token,
                self.location_id,
                converted_items,
                self.use_production,
                customer_name=customer_name,
                phone_number=phone_number,
                fulfillment_type=fulfillment_type,
                schedule_type=schedule_type,
                pickup_time=pickup_time,
                prep_time_duration=prep_time_duration,
            )

            if not created_order:
                return "Failed to create order."

            # Step 4: Create payment link
            logger.debug("[SquareTool] Step 4: Creating payment link")
            total_quantity = sum(item["quantity"] for item in converted_items)
            payment_link = self._create_payment_link(created_order, total_quantity)

            if payment_link:
                payment_url = payment_link.url or payment_link.long_url
                # update order id to use the newly generated one from payment link request
                created_order.id = payment_link.order_id
            else:
                payment_url = None

            # Persist order and transaction records
            try:
                self._save_order_to_db(created_order, converted_items, payment_url)
            except Exception as e:
                logger.error(
                    "[SquareTool.create_order_and_payment_link] Failed to save order to database, continuing despite DB save failure",
                    exc_info=e,
                )

            if not payment_url:
                return f"Order created (ID: {created_order.id}) but failed to create payment link."

            # Format success response using utility function
            return format_order_success_message(
                created_order=created_order,
                location_id=self.location_id,
                matched_items=converted_items,
                payment_url=payment_url,
            )

        except Exception as e:
            logger.error(f"[SquareTool.create_order_and_payment_link] Error: {e}")
            return "Failed to create order and payment link. Please try again."
