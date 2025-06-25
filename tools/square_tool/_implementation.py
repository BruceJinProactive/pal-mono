import uuid
from functools import cached_property
from typing import Optional

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import tool

from agent.tool import ToolMetadata
from agent.tool.internal.query_messages_tool import QueryMessagesTool
from tools.square_tool._apis import create_payment_link, search_catalog
from tools.square_tool._utils import (
    create_comprehensive_menu,
    create_square_order_with_modifiers,
    extract_items_with_modifiers_from_chat,
    format_order_success_message,
    match_items_to_catalog_with_modifiers,
)
from tools.square_tool.classes import (
    CatalogItemObject,
    CatalogQuery,
    CheckoutOptions,
    CreatePaymentLinkInput,
    Order,
    SearchCatalogInput,
    SquareAccessToken,
    TextQuery,
)
from utils.log import logger
from tools.utils.ordering._utils import get_chat_history


class SquareTool(Toolkit):
    """
    Main Square Tool implementation for POS, payments, and catalog operations.
    """

    def __init__(
        self,
        access_token: str,
        location_id: str,
        tool_metadata: Optional[ToolMetadata] = None,
        use_production: bool = False,
    ):
        super().__init__(name="square_tool")

        self.tool_metadata = tool_metadata
        self.use_production = use_production
        self.location_id = location_id
        self.access_token = access_token

        # Initialize query messages tool if metadata is provided
        if self.tool_metadata:
            self.query_messages_tool = QueryMessagesTool(self.tool_metadata)
        else:
            self.query_messages_tool = None

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

    def _find_first_variation_for_item(self, item_name: str) -> Optional[str]:
        """Find the first valid variation ID for a given item name."""
        try:
            search_response = search_catalog(
                self._square_token,
                SearchCatalogInput(
                    query=CatalogQuery(text_query=TextQuery(keywords=[item_name])),
                    object_types=["ITEM"],
                    include_related_objects=False,  # type: ignore
                    include_category_path_to_root=False,  # type: ignore
                    limit=1,  # Only need the first match
                    use_production=self.use_production,
                ),
            )

            items = search_response.objects or []
            if not items:
                return None

            # Take the first item found
            first_item = items[0]
            if first_item.type != "ITEM" or not isinstance(
                first_item, CatalogItemObject
            ):
                return None

            # Check if item has variations
            if (
                not hasattr(first_item.item_data, "variations")
                or not first_item.item_data.variations
            ):
                return None

            # Take the first variation with price
            first_variation = first_item.item_data.variations[0]
            if (
                not hasattr(first_variation, "item_variation_data")
                or not first_variation.item_variation_data
            ):
                return None

            var_data = first_variation.item_variation_data
            if not hasattr(var_data, "price_money") or not var_data.price_money:
                return None

            return first_variation.id

        except Exception as e:
            logger.error(
                f"[SquareTool._find_first_variation_for_item] Error finding variation for {item_name}: {e}"
            )
            return None

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

    @tool
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
        latest_user_message: Optional[str] = None,
        chat_history: Optional[str] = None,
    ) -> str:
        """
        **WHEN TO USE THIS TOOL:**
        - When the customer has CONFIRMED they want to place/complete their order
        - When the customer says things like: "checkout", "pay now", "place order", "complete order", "finalize order"
        - When the customer has finished adding items and is ready to pay
        - When all required ordering information has been collected through the conversation

        **DO NOT USE THIS TOOL WHEN:**
        - Customer is just browsing the menu or asking questions
        - Customer is still deciding what to order
        - Customer hasn't confirmed they want to proceed with payment
        - Customer is just asking about prices or availability

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

            # Get chat history
            if chat_history is None:
                chat_history = get_chat_history(
                    self.query_messages_tool,
                    latest_user_message if latest_user_message else "",
                )

            # Step 1: Extract items with modifiers from chat history
            logger.info(
                "[SquareTool] Step 1: Extracting items with modifiers from chat history"
            )
            items_with_modifiers = extract_items_with_modifiers_from_chat(chat_history)

            if not items_with_modifiers:
                return "No food items found in the conversation history."

            logger.info(
                f"[SquareTool] Found {len(items_with_modifiers)} items to order"
            )

            # Step 2: Match items to catalog with exact names
            logger.info("[SquareTool] Step 2: Matching items to catalog")
            matched_items = match_items_to_catalog_with_modifiers(items_with_modifiers)

            if not matched_items:
                return (
                    "Could not find any of the requested items in the Square catalog."
                )

            # Check if some items weren't found
            missing_items = []
            matched_item_names = {item["item_name"] for item in matched_items}
            for item_dict in items_with_modifiers:
                if item_dict["item_name"] not in matched_item_names:
                    missing_items.append(item_dict["item_name"])

            # Step 3: Create order with modifiers
            logger.info("[SquareTool] Step 3: Creating Square order with modifiers")
            created_order = create_square_order_with_modifiers(
                self._square_token, self.location_id, matched_items, self.use_production
            )

            if not created_order:
                return "Failed to create order."

            # Step 4: Create payment link
            logger.info("[SquareTool] Step 4: Creating payment link")
            total_quantity = sum(item["quantity"] for item in matched_items)
            payment_url = self._create_payment_link(created_order, total_quantity)

            if not payment_url:
                return f"Order created (ID: {created_order.id}) but failed to create payment link."

            # Format success response using utility function
            return format_order_success_message(
                created_order=created_order,
                location_id=self.location_id,
                matched_items=matched_items,
                payment_url=payment_url,
                missing_items=missing_items if missing_items else None,
            )

        except Exception as e:
            logger.error(f"[SquareTool.create_order_and_payment_link] Error: {e}")
            return "Failed to create order and payment link. Please try again."
