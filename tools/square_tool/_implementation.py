import json
import uuid
from functools import cached_property
from typing import Optional

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import tool
from pydantic import ValidationError

from agent.tool import ToolMetadata
from agent.tool.internal.query_messages_tool import QueryMessagesTool
from tools.square_tool._apis import create_payment_link
from tools.square_tool._prompt_constants import (
    RETRIEVE_ORDER_ITEMS_SYSTEM_PROMPT,
    SQUARE_EXTRACTOR_SYSTEM_PROMPT_V2,
    SQUARE_EXTRACTOR_USER_PROMPT_V2,
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
        access_token (str): Square API access token
        location_id (str): Square location ID
        namespace (str): Pinecone namespace containing the catalog documents
        index_name (str): Pinecone index name
        tool_metadata (ToolMetadata): Tool metadata for chat history access
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
        access_token: str,
        location_id: str,
        namespace: str,
        index_name: str,
        tool_metadata: ToolMetadata,
        use_production: bool = False,
    ):
        super().__init__(name="square_tool")

        self.tool_metadata = tool_metadata
        self.use_production = use_production
        self.location_id = location_id
        self.access_token = access_token
        self.namespace = namespace
        self.index_name = index_name

        # Initialize query messages tool
        self.query_messages_tool = QueryMessagesTool(self.tool_metadata)

        # Initialize Pinecone query engine for catalog retrieval
        self.query_engine = create_query_engine(
            namespace=self.namespace, index_name=self.index_name
        )

        # Register tools
        self.register(self.create_order_and_payment_link)

    @cached_property
    def _square_token(self) -> SquareAccessToken:
        """
        Returns the Square API access token provided during initialization.

        Returns:
            SquareAccessToken: An object containing the access token for Square API calls.
        """
        with LLMObs.task(name="get_square_token"):
            bearer_token = SquareAccessToken(
                access_token=self.access_token,
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
    ) -> Optional[str]:
        """Create payment link using the actual order and return URL."""
        try:
            payment_link_response = create_payment_link(
                self._square_token,
                CreatePaymentLinkInput(  # type: ignore
                    idempotency_key=str(uuid.uuid4()),
                    description=f"Order payment for {total_item_count} items",
                    order=order,  # Use the actual order object
                    checkout_options=CheckoutOptions(  # type: ignore
                        allow_tipping=True,
                        ask_for_shipping_address=False,
                        enable_coupon=False,
                        enable_loyalty=False,
                    ),
                    payment_note="Palona AI testing - Square order payment",
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

            return (
                payment_link_response.payment_link.url
                or payment_link_response.payment_link.long_url
            )

        except Exception as e:
            logger.error(f"[SquareTool._create_payment_link] Error: {e}")
            return None

    def _construct_order(
        self, latest_user_message: str, provided_chat_history: Optional[str] = None
    ) -> ExtractedOrderWithModifiers | str:
        """
        Construct order from chat history using Pinecone retrieval and LLM extraction.

        Args:
            latest_user_message (str): The latest user message.

        Returns:
            ExtractedOrderWithModifiers | str: Extracted order or error message.
        """
        # Use provided chat history or get it from the standardized functions

        chat_history = get_chat_history(self.query_messages_tool, latest_user_message)

        context = get_relevant_docs(
            self.query_engine,
            chat_history,
            RETRIEVE_ORDER_ITEMS_SYSTEM_PROMPT,
            SubQueries,
        )

        order = llm_call(
            system_prompt=SQUARE_EXTRACTOR_SYSTEM_PROMPT_V2,
            prompt=SQUARE_EXTRACTOR_USER_PROMPT_V2.format(
                context=context, chat_history=chat_history
            ),
            response_format=ExtractedOrderWithModifiers,
            reasoning=False,
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

            logger.info(
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
    def create_order_and_payment_link(
        self,
        latest_user_message: str,
    ) -> str:
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

        Args:
            latest_user_message: The latest message from the user to include in chat history

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
            logger.info(
                "[SquareTool] Step 1: Extracting items with modifiers from chat history using Pinecone retrieval"
            )
            extracted_order = self._construct_order(latest_user_message)

            if isinstance(extracted_order, str):
                return extracted_order  # Return error message

            if not extracted_order.items:
                return "No food items found in the conversation history."

            logger.info(
                f"[SquareTool] Found {len(extracted_order.items)} items to order"
            )

            # Step 2: Validate extracted order
            logger.info("[SquareTool] Step 2: Validating extracted order")
            is_valid, error_message, converted_items = self._validate_extracted_order(
                extracted_order
            )

            if not is_valid:
                return error_message

            # Step 3: Create order with modifiers
            logger.info("[SquareTool] Step 3: Creating Square order with modifiers")

            # Get customer name and phone number
            customer_name = extracted_order.customer_name
            phone_number = extracted_order.phone_number

            created_order = create_square_order_with_modifiers(
                self._square_token,
                self.location_id,
                converted_items,
                self.use_production,
                customer_name=customer_name,
                phone_number=phone_number,
            )

            if not created_order:
                return "Failed to create order."

            # Step 4: Create payment link
            logger.info("[SquareTool] Step 4: Creating payment link")
            total_quantity = sum(item["quantity"] for item in converted_items)
            payment_url = self._create_payment_link(created_order, total_quantity)

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
