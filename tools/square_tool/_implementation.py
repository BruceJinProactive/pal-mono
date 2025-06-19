import uuid
from functools import cached_property
from typing import List, Optional

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import tool

from agent.tool import ToolMetadata
from agent.tool.internal.query_messages_tool import QueryMessagesTool
from tools.square_tool._apis import (
    create_order,
    create_payment_link,
    list_catalog,
    search_catalog,
)
from tools.square_tool._prompt_constants import (
    SQUARE_FOOD_EXTRACTION_SYSTEM_PROMPT,
    SQUARE_FOOD_EXTRACTION_USER_PROMPT,
)
from tools.square_tool._utils import extract_customer_menu
from tools.square_tool.classes import (
    CatalogItemObject,
    CatalogQuery,
    CheckoutOptions,
    CreateOrderInput,
    CreatePaymentLinkInput,
    ListCatalogInput,
    Order,
    OrderLineItem,
    SearchCatalogInput,
    SquareAccessToken,
    SquareFoodItemList,
    TextQuery,
)
from utils.log import logger
from utils.ordering._utils import construct_order, get_chat_history


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
        self.register(self.list_catalog_customer_menu)
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
            input_data = ListCatalogInput(
                cursor=None,
                types=None,
                catalog_version=None,
                use_production=self.use_production,
            )

            catalog_response = list_catalog(
                access_token=self._square_token,
                input_data=input_data,
            )

            return extract_customer_menu(catalog_response)

        except Exception as e:
            logger.error(f"[SquareTool._get_menu_info] Error: {e}")
            return "Menu information not available"

    def _extract_food_items(self, chat_history: str) -> List[tuple]:
        """Extract food items from chat history using menu context."""
        try:
            menu_info = self._get_menu_info()

            system_prompt = SQUARE_FOOD_EXTRACTION_SYSTEM_PROMPT.format(
                menu_info=menu_info
            )
            user_prompt = SQUARE_FOOD_EXTRACTION_USER_PROMPT.format(
                chat_history=chat_history
            )

            food_items_result = construct_order(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_format=SquareFoodItemList,
                error_prefix="Failed to extract food items",
            )

            if isinstance(food_items_result, str):
                logger.error(
                    f"[SquareTool._extract_food_items] Error: {food_items_result}"
                )
                return []

            # Return list of (item_name, quantity) tuples
            food_items = []
            for item in food_items_result.items:
                food_items.append((item.item_name, item.quantity))

            return food_items

        except Exception as e:
            logger.error(f"[SquareTool._extract_food_items] Error: {e}")
            return []

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

    def _find_catalog_variations(self, food_items: List[tuple]) -> List[tuple]:
        """Find catalog variation IDs for food items with quantities."""
        variation_items = []

        for item_name, quantity in food_items:
            variation_id = self._find_first_variation_for_item(item_name)

            if variation_id:
                variation_items.append((variation_id, quantity))
                logger.info(
                    f"[SquareTool] Found variation {variation_id} for {item_name} (qty: {quantity})"
                )
            else:
                logger.warning(f"[SquareTool] No variation found for: {item_name}")

        return variation_items

    def _create_square_order(self, variation_items: List[tuple]) -> Optional[Order]:
        """Create Square order and return the full Order object."""
        try:
            line_items = [
                OrderLineItem(quantity=str(quantity), catalog_object_id=variation_id)  # type: ignore
                for variation_id, quantity in variation_items
            ]

            order_response = create_order(
                self._square_token,
                CreateOrderInput(
                    order=Order(location_id=self.location_id, line_items=line_items),  # type: ignore
                    idempotency_key=str(uuid.uuid4()),
                    use_production=self.use_production,
                ),
            )

            if order_response.errors:
                logger.error(
                    f"[SquareTool._create_square_order] Errors: {order_response.errors}"
                )
                return None

            if not order_response.order:
                logger.error("[SquareTool._create_square_order] No order returned")
                return None

            logger.info(
                f"[SquareTool] Order created successfully: {order_response.order.id}"
            )
            return order_response.order  # Return full Order object

        except Exception as e:
            logger.error(f"[SquareTool._create_square_order] Error: {e}")
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
                    payment_note="Square order payment",
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
    def list_catalog_customer_menu(
        self,
    ) -> str:
        """
        Get a customer-friendly menu from Square catalog.

        Use this tool to show customers available menu items, prices, and dietary information.

        Returns:
            str: Customer-friendly food catalog information
        """
        try:
            # Ensure we can get the token
            token = self._square_token

            # Create input model for validation
            input_data = ListCatalogInput(
                cursor=None,
                types=None,
                catalog_version=None,
                use_production=self.use_production,
            )

            # Call the API function
            catalog_response = list_catalog(
                access_token=token,
                input_data=input_data,
            )

            # Return simple customer menu
            return extract_customer_menu(catalog_response)

        except Exception as e:
            logger.error(
                f"[SquareTool.list_catalog_customer_menu] Error getting menu: {e}"
            )
            return "Failed to get the menu, please try again."

    @tool
    def create_order_and_payment_link(
        self, latest_user_message: Optional[str] = None
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
            chat_history = get_chat_history(
                self.query_messages_tool,
                latest_user_message if latest_user_message else "",
            )

            # Step 1: Extract food items from chat history
            logger.info("[SquareTool] Step 1: Extracting food items from chat history")
            food_items = self._extract_food_items(chat_history)

            if not food_items:
                return "No food items found in the conversation history."

            logger.info(
                f"[SquareTool] Found {len(food_items)} items to order: {food_items}"
            )

            # Step 2: Find catalog variations
            logger.info("[SquareTool] Step 2: Finding catalog variations")
            variation_items = self._find_catalog_variations(food_items)

            if not variation_items:
                return (
                    "Could not find any of the requested items in the Square catalog."
                )

            # Step 3: Create order
            logger.info("[SquareTool] Step 3: Creating Square order")
            created_order = self._create_square_order(variation_items)

            if not created_order:
                return "Failed to create order."

            # Step 4: Create payment link
            logger.info("[SquareTool] Step 4: Creating payment link")
            payment_url = self._create_payment_link(created_order, len(variation_items))

            if not payment_url:
                return f"Order created (ID: {created_order.id}) but failed to create payment link."

            # Format success response
            return f"""Order created successfully!
Order ID: {created_order.id}
Location: {self.location_id}
Items: {len(variation_items)} items
Payment Link: {payment_url}"""

        except Exception as e:
            logger.error(f"[SquareTool.create_order_and_payment_link] Error: {e}")
            return "Failed to create order and payment link. Please try again."
