"""
MenuSifu Tool implementation for online ordering and checkout
"""

import json
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs.decorators import tool
from pydantic import ValidationError

from agent.tool import ToolMetadata
from agent.tool.internal.query_messages_tool import QueryMessagesTool
from tools.menusifu_tool._apis import calculate_order_total, generate_order
from tools.menusifu_tool._prompt_constants import (
    MENUSIFU_EXTRACTOR_SYSTEM_PROMPT,
    MENUSIFU_EXTRACTOR_USER_PROMPT,
    RETRIEVE_ORDER_ITEMS_SYSTEM_PROMPT,
)
from tools.menusifu_tool._utils import (
    build_address_info,
    build_customer_info,
    build_order_price_from_calculation,
    extract_order_summary,
)
from tools.menusifu_tool.classes import (
    ExtractedMenuSifuOrder,
    OrderCalculationRequest,
    OrderCalculationResponse,
    OrderGenerationRequest,
    OrderGenerationResponse,
    OrderGenerationSelectedItem,
    OrderItemOptionNote,
    OrderSelectedItem,
    OrderType,
    PaymentMethod,
)
from tools.utils.ordering._llm import llm_call
from tools.utils.ordering._query_engine import create_query_engine
from tools.utils.ordering._utils import get_chat_history, get_relevant_docs
from tools.utils.ordering.classes import SubQueries
from utils.log import logger
from utils.secret import get_client_secret_with_fallback


def _convert_extracted_order_to_dict(
    extracted_order: ExtractedMenuSifuOrder,
) -> List[Dict[str, Any]]:
    """
    Convert ExtractedMenuSifuOrder to internal dict format for processing.

    Args:
        extracted_order: Extracted order from LLM

    Returns:
        List of item dictionaries in internal format
    """
    processed_items = []
    for item in extracted_order.items:
        # Convert modifiers to dict format for compatibility
        options_list = []
        for modifier in item.modifiers:
            option_dict = {
                "id": modifier.id,
                "name": modifier.name,
                "price": modifier.price,
                "quantity": modifier.quantity,
                "checked": modifier.checked,
            }
            options_list.append(option_dict)

        item_dict = {
            "id": item.item_id,
            "item_id": item.item_id,
            "sale_item_id": item.sale_item_id,
            "name": item.item_name,
            "quantity": item.quantity,
            "price": item.price,
            "display_price": item.display_price,
            "item_type": item.item_type,
            "category_id": item.category_id,
            "special_notes": item.special_notes,
            "options": options_list,  # Converted modifiers to options dict format
        }
        processed_items.append(item_dict)

    return processed_items


def _safe_convert_item_fields(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Safely convert item fields with proper validation and defaults.

    Args:
        item: Raw item dictionary from order data

    Returns:
        Dict with safely converted fields

    Raises:
        ValueError: If required fields are missing
    """
    # Safely extract and validate required id field
    raw_id = item.get("id") or item.get("item_id")
    if raw_id is None or raw_id == "":
        raise ValueError(f"Item missing required 'id' field: {item}")
    item_id = int(raw_id)

    # Safely extract sale_item_id with fallback to item_id
    raw_sale_item_id = item.get("saleItemId") or item.get("sale_item_id") or raw_id
    sale_item_id = int(raw_sale_item_id)

    # Safely convert price with validation (required field, default to 0)
    raw_price = item.get("price")
    if raw_price is None or raw_price == "":
        price_val = Decimal("0")
    else:
        price_val = Decimal(str(raw_price))

    # Safely convert displayPrice (optional field) - keep raw value intact
    raw_display_price = item.get("displayPrice") or item.get("display_price")
    display_price_val = raw_display_price  # Keep as-is without any modifications

    # Safely convert categoryId with default
    raw_category_id = item.get("categoryId") or item.get("category_id")
    category_id_val = int(raw_category_id) if raw_category_id else 0

    # Safely convert quantity with default
    raw_quantity = item.get("quantity")
    quantity_val = int(raw_quantity) if raw_quantity else 1

    return {
        "id": item_id,
        "saleItemId": sale_item_id,
        "price": price_val,
        "displayPrice": display_price_val,  # Raw value kept intact
        "categoryId": category_id_val,
        "quantity": quantity_val,
        "itemType": item.get("itemType") or item.get("item_type") or "SALE_ITEM",
        "name": item.get("name") or "",
    }


def _safe_convert_option_fields(option: Dict[str, Any]) -> Dict[str, Any]:
    """
    Safely convert option fields with proper validation and defaults.

    Args:
        option: Raw option dictionary from item data

    Returns:
        Dict with safely converted fields
    """
    # Safely convert optionPrice (optional field)
    raw_option_price = option.get("optionPrice")
    option_price_val = None
    if raw_option_price is not None and raw_option_price != "":
        option_price_val = Decimal(str(raw_option_price))

    # Safely convert option price (required field, default to 0)
    raw_price = option.get("price")
    if raw_price is None or raw_price == "":
        price_val = Decimal("0")
    else:
        price_val = Decimal(str(raw_price))

    # Safely convert option quantity with default
    raw_quantity = option.get("quantity")
    quantity_val = int(raw_quantity) if raw_quantity else 1

    return {
        "id": option.get("id"),  # Can be None for optional options
        "optionPrice": option_price_val,
        "price": price_val,
        "quantity": quantity_val,
        "name": option.get("name") or "",
        "checked": option.get("checked", True),
        "isOpenOption": option.get("isOpenOption", False),
    }


class MenuSifuTool(Toolkit):
    """
    MenuSifu Tool for online ordering and checkout operations.

    This tool provides comprehensive order calculation and order generation
    functionality for MenuSifu restaurants. It uses Pinecone knowledge base for
    menu item retrieval and ID mapping, following the Square tool pattern.

    Constructor Parameters:
        merchant_id (str): MenuSifu merchant identifier
        namespace (str): Pinecone namespace containing the menu catalog documents
        index_name (str): Pinecone index name
        tool_metadata (ToolMetadata): Tool metadata for chat history access
        base_url (str): MenuSifu API base URL (default: assistant.mealkeyway.com)
    """

    def __init__(
        self,
        merchant_id: str,
        namespace: str,
        index_name: str,
        tool_metadata: ToolMetadata,
        base_url: str = "assistant.mealkeyway.com",
    ):
        """
        Initialize MenuSifu Tool.

        Args:
            merchant_id: MenuSifu merchant identifier
            namespace: Pinecone namespace containing menu catalog
            index_name: Pinecone index name
            tool_metadata: Tool metadata containing session information
            base_url: MenuSifu API base URL
        """
        super().__init__(name="menusifu_tool")

        self.tool_metadata = tool_metadata
        self.merchant_id = merchant_id
        self.base_url = base_url
        self.namespace = namespace
        self.index_name = index_name

        # Initialize query messages tool for chat history access
        self.query_messages_tool = QueryMessagesTool(self.tool_metadata)

        # Initialize Pinecone query engine for menu catalog retrieval
        self.query_engine = create_query_engine(
            namespace=self.namespace, index_name=self.index_name
        )

        # Register tools
        self.register(self.create_order_checkout)

        logger.debug(
            f"MenuSifuTool instance created: merchant_id={merchant_id}, base_url={base_url}"
        )

    @property
    def _menusifu_token(self) -> str:
        """
        Returns the MenuSifu API access token from secret manager.
        Access token is fetched from the secret manager using MENUSIFU_ACCESS_TOKEN key.

        Returns:
            str: Access token for MenuSifu API calls.

        Raises:
            ValueError: If no access token is available from secret manager
        """
        try:
            access_token = get_client_secret_with_fallback("MENUSIFU_ACCESS_TOKEN")
            if not access_token:
                logger.error("No MenuSifu access token found in secret manager")
                raise ValueError(
                    "MenuSifu access token is required - check MENUSIFU_ACCESS_TOKEN secret"
                )

            return access_token
        except Exception as e:
            logger.error(
                f"Failed to retrieve MenuSifu access token from secret manager: {e}"
            )
            raise ValueError(f"Failed to retrieve MenuSifu access token: {e}") from e

    def _extract_order_from_chat(self) -> Union[ExtractedMenuSifuOrder, str]:
        """
        Extract order information from chat history using Pinecone retrieval and LLM extraction.

        Returns:
            ExtractedMenuSifuOrder or error message string
        """
        try:
            # Step 1: Get chat history using standardized helper function
            chat_history = get_chat_history(self.query_messages_tool)
            if not chat_history.strip():
                return "No recent messages found to extract order information from chat history"

            # Step 2: Get relevant menu context from knowledge base using Pinecone
            context = get_relevant_docs(
                self.query_engine,
                chat_history,
                RETRIEVE_ORDER_ITEMS_SYSTEM_PROMPT,
                SubQueries,
            )

            # Step 3: Use LLM to extract order information with menu context
            extracted_order = llm_call(
                system_prompt=MENUSIFU_EXTRACTOR_SYSTEM_PROMPT,
                prompt=MENUSIFU_EXTRACTOR_USER_PROMPT.format(
                    context=context,
                    chat_history=chat_history,
                ),
                response_format=ExtractedMenuSifuOrder,
                openai=False,  # Use internal model like Square
            )

            # Check if the order is a string and convert it to an ExtractedMenuSifuOrder object
            if extracted_order is None:
                return "Failed to extract order information from chat history"

            if isinstance(extracted_order, str):
                try:
                    order_dict = json.loads(extracted_order)
                    extracted_order = ExtractedMenuSifuOrder(**order_dict)
                except (json.JSONDecodeError, ValueError) as e:
                    return f"Failed to parse extracted order: {str(e)}"

            if not isinstance(extracted_order, ExtractedMenuSifuOrder):
                return f"Order extraction returned unexpected type: {type(extracted_order)}"

            # Validate minimum required fields
            if not extracted_order.customer_first_name:
                return "Customer first name is required for order processing"

            if not extracted_order.items:
                return "Some required items are missing from the order; please check inputs"

            logger.debug(f"[MenuSifuTool] Extracted order: {extracted_order}")
            return extracted_order

        except ValidationError as e:
            logger.warning(f"[MenuSifuTool] Order validation error: {e}")
            warning_message = ""
            for error in e.errors():
                logger.warning(
                    f"Missing or invalid order data in the response: {error}"
                )
                warning_message += f"Missing or invalid order data: {error['loc'][-1]}: {error['msg']}, input: {error.get('input', 'N/A')}\n"
            return (
                warning_message
                + "\nAsk the customer to provide the missing information or correct the invalid details."
            )
        except Exception as e:
            logger.error(f"[MenuSifuTool] Order extraction failed: {e}")
            return f"Failed to extract order information: {str(e)}"

    def _process_extracted_order(
        self, extracted_order: Union[ExtractedMenuSifuOrder, str]
    ) -> Union[List[Dict], str]:
        """
        Process the extracted order and return items or error message.

        Args:
            extracted_order: Extracted order from LLM (Pydantic model or error string)

        Returns:
            List of processed items or error message string
        """
        # Return error string directly
        if isinstance(extracted_order, str):
            return extracted_order

        # Convert ExtractedMenuSifuOrder to internal dict format
        return _convert_extracted_order_to_dict(extracted_order)

    def _calculate_order_total(
        self, order_items: List[Dict]
    ) -> Union[OrderCalculationResponse, str]:
        """
        Calculate order total using MenuSifu calculation API.

        Args:
            order_items: List of selected items with quantities

        Returns:
            OrderCalculationResponse or error message
        """
        try:
            # Always use pickup order type (delivery not supported)
            # Validate that order_items is non-empty
            if not order_items:
                return "Cannot calculate order total: no items provided"

            # Convert order_items to OrderSelectedItem instances
            selected_items = []
            for item in order_items:
                try:
                    # Use helper function for safe field conversion
                    safe_fields = _safe_convert_item_fields(item)

                    # Use raw displayPrice for OrderSelectedItem
                    display_price_val = safe_fields["displayPrice"]

                    # Map fields from order_items to OrderSelectedItem format
                    selected_item = OrderSelectedItem(
                        categoryId=safe_fields["categoryId"],
                        displayPrice=display_price_val,
                        id=safe_fields["id"],
                        itemType=safe_fields["itemType"],
                        name=safe_fields["name"],
                        nameMultilingual=None,  # Optional field
                        options=item.get("options") or [],  # List of options/modifiers
                        price=safe_fields["price"],
                        quantity=safe_fields["quantity"],
                        saleItemId=safe_fields["saleItemId"],
                        # Optional detail price fields
                        detailPriceId=None,
                        sizeId=None,
                        detailPriceInfo=None,
                    )
                    selected_items.append(selected_item)

                except Exception as e:
                    return f"Failed to convert item '{item.get('name', 'Unknown item')}': {str(e)}"

            if not selected_items:
                return "No valid items could be processed for calculation"

            # Create calculation request with actual items
            calc_request = OrderCalculationRequest(
                orderType=OrderType.ONLINE_PICKUP,  # Always pickup
                paymentMethod=PaymentMethod.CASH,
                totalTips=Decimal("0"),  # Default, user can specify
                deliveryFee=Decimal("0"),  # Always 0 for pickup
                selectedItems=selected_items,  # Use actual converted items
            )

            # Call calculation API
            logger.info(
                f"Calling MenuSifu order calculation API with {len(selected_items)} items"
            )
            calc_result = calculate_order_total(
                access_token=self._menusifu_token,
                merchant_id=self.merchant_id,
                order_request=calc_request,
                base_url=self.base_url,
            )

            # Return OrderCalculationResponse directly, or convert error response to string
            if isinstance(calc_result, OrderCalculationResponse):
                return calc_result
            else:
                return f"Order calculation failed: {calc_result}"

        except Exception as e:
            return f"Failed to calculate order total: {str(e)}"

    def _generate_order(
        self,
        calc_result: OrderCalculationResponse,
        customer_info: Union[ExtractedMenuSifuOrder, str],
        order_items: List[Dict],
    ) -> Union[OrderGenerationResponse, str]:
        """
        Generate order using MenuSifu order generation API.

        Args:
            calc_result: Result from order calculation
            customer_info: Customer information
            order_items: List of selected items with quantities

        Returns:
            OrderGenerationResponse or error message
        """
        try:
            # Always use pickup order type (delivery not supported)
            # Validate that order_items is non-empty
            if not order_items:
                return "Cannot generate order: no items provided"

            # Handle error case where customer_info is an error string
            if isinstance(customer_info, str):
                return customer_info

            # Extract customer info directly from the unified extraction result
            # At this point, customer_info must be ExtractedMenuSifuOrder (str case handled above)
            customer_email = customer_info.customer_email or "test@palona.com"
            customer_first_name = customer_info.customer_first_name
            customer_last_name = customer_info.customer_last_name or ""

            # Handle phone information from structured Phone object
            if not customer_info.customer_phone:
                return f"Customer phone number is required for order processing. Customer: {customer_first_name} {customer_last_name} ({customer_email})"

            country_code = customer_info.customer_phone.country_code
            phone_number = customer_info.customer_phone.number
            payment_method_str = "CASH"  # Hardcoded to cash as requested
            # Address fields not needed for pickup orders

            # Validate that normalized phone_number is non-empty
            if not phone_number or phone_number.strip() == "":
                return f"Customer phone number is required for order processing. Customer: {customer_first_name} {customer_last_name} ({customer_email})"

            # Build customer using helper function
            customer = build_customer_info(
                email=customer_email,
                first_name=customer_first_name,
                last_name=customer_last_name,
                country_code=country_code,
                phone_number=phone_number,
            )

            # Build empty address for pickup orders
            address = build_address_info()  # Always empty address for pickup

            # Build order price from calculation using helper function
            order_price = build_order_price_from_calculation(calc_result)

            # Convert order_items to OrderGenerationSelectedItem instances
            selected_items = []
            for item in order_items:
                try:
                    # Use helper function for safe field conversion
                    safe_fields = _safe_convert_item_fields(item)

                    # Convert options/modifiers to OrderItemOptionNote using helper
                    item_options = []
                    if item.get("options"):
                        for option in item["options"]:
                            safe_option_fields = _safe_convert_option_fields(option)

                            option_note = OrderItemOptionNote(
                                id=safe_option_fields["id"],
                                detailPriceId=None,  # Optional field
                                optionPrice=safe_option_fields["optionPrice"],
                                name=safe_option_fields["name"],
                                price=safe_option_fields["price"],
                                quantity=safe_option_fields["quantity"],
                                checked=safe_option_fields["checked"],
                                isOpenOption=safe_option_fields["isOpenOption"],
                            )
                            item_options.append(option_note)

                    # Use raw displayPrice for OrderGenerationSelectedItem (keep intact)
                    display_price_val = safe_fields["displayPrice"]

                    # Create OrderGenerationSelectedItem
                    selected_item = OrderGenerationSelectedItem(
                        id=safe_fields["id"],
                        saleItemId=safe_fields["saleItemId"],
                        quantity=safe_fields["quantity"],
                        price=safe_fields["price"],
                        displayPrice=display_price_val,
                        itemType=safe_fields["itemType"],
                        name=safe_fields["name"],
                        nameMultilingual=None,  # Optional field
                        categoryId=safe_fields["categoryId"],
                        options=item_options if item_options else None,
                    )
                    selected_items.append(selected_item)
                except Exception as e:
                    return f"Failed to process item '{item.get('name', 'Unknown item')}': {str(e)}"

            if not selected_items:
                return "No valid items could be processed for order generation"

            # Extract payment method from customer_data (already extracted above)
            payment_method_str = payment_method_str.upper()
            if (
                payment_method_str == "CREDIT_CARD"
                or payment_method_str == "CARD"
                or payment_method_str == "CREDIT"
            ):
                payment_method = PaymentMethod.CREDIT_CARD
                pay_online = True
            elif payment_method_str == "WECHAT":
                payment_method = PaymentMethod.WECHAT_PAY
                pay_online = True
            else:
                payment_method = PaymentMethod.CASH
                pay_online = False

            # Create order generation request
            order_request = OrderGenerationRequest(
                countryCode=country_code,
                telephoneNumber=phone_number,
                channel="WEB",  # Changed from "BOT" to match sample
                productLine="ONLINE_ORDER",
                orderType=OrderType.ONLINE_PICKUP,  # Always pickup
                price=order_price,
                customer=customer,
                address=address,
                paymentMethod=payment_method,  # Use extracted payment method
                paymentInfo="",
                payOnline=pay_online,
                selectedItems=selected_items,  # Use converted items
                # Required additional fields
                needSms=False,
                riskifiedId=None,
                pointRule=None,
                _id=None,
                # Additional fields with defaults (matching sample values)
                onlineType="ONLINE_PICKUP",  # Always pickup
                deliveryInfo={},  # Always empty for pickup
                selectedGiftItems=[],
                selectedGiftItemsCrm=[],
                allergyInfo="",
                needUtensils=True,  # Changed from False to match sample
                needStraws=True,  # Changed from False to match sample
                needCondiments=True,  # Changed from False to match sample
                miniProgram=False,
                businessId=None,
            )

            # Call order generation API
            order_result = generate_order(
                access_token=self._menusifu_token,
                merchant_id=self.merchant_id,
                order_request=order_request,
                base_url=self.base_url,
            )

            # Return result directly - it's either OrderGenerationResponse or error string
            return order_result

        except Exception as e:
            return f"Failed to generate order: {str(e)}"

    @tool
    def create_order_checkout(
        self,
        customer_name: Optional[str] = None,
        phone_number: Optional[str] = None,
        special_instructions: Optional[str] = None,
    ) -> str:
        """
        Create and place a MenuSifu order for the customer.

        **When to use this tool:**
        - Customer explicitly requests to place/complete/finalize their order
        - Customer says things like: "checkout", "place order", "complete order", "finalize order"
        - Customer has finished selecting items and confirmed they want to proceed
        - All required ordering information has been collected through conversation

        **Expected behavior:**
        - Extracts order details, customer info, and items from chat history
        - Calculates order total and generates the order with MenuSifu
        - Returns order confirmation with totals and order ID

        **Do not use when:**
        - Customer is browsing menu or asking questions about items
        - Customer is still deciding what to order or quantities
        - Customer hasn't confirmed they want to proceed with order
        - Missing required information (customer name, phone, items)

        Args:
            customer_name: Customer's full name for the order.
            phone_number: Customer's phone number for order pickup.
            special_instructions: Special requests or notes for the order.

        Note: All parameters are optional placeholders. Actual values are extracted from chat history.

        Returns:
            str: Order confirmation with details and order ID, or error message if order cannot be processed.
        """
        try:
            logger.info("[MenuSifuTool] Starting order checkout process")

            # Note: Parameters are placeholder documentation only.
            # Customer name, phone, and items are extracted from chat.
            # Email is fixed to test@palona.com, order type is always pickup, and payment method is always cash.

            # Check if we have query messages tool
            if not self.query_messages_tool:
                return (
                    "Chat history access not available. Please provide tool metadata."
                )

            # Step 1: Extract order from chat
            logger.info("[MenuSifuTool] Step 1: Extracting order from chat history")
            extracted_order = self._extract_order_from_chat()

            # Step 2: Process extracted order
            logger.info("[MenuSifuTool] Step 2: Processing extracted order")
            processed_items = self._process_extracted_order(extracted_order)
            if isinstance(processed_items, str):
                return processed_items  # Error message

            # Step 3: Calculate order total
            logger.info("[MenuSifuTool] Step 3: Calculating order total")
            calc_result = self._calculate_order_total(processed_items)
            if isinstance(calc_result, str):
                return calc_result  # Error message

            # Step 4: Generate order
            logger.info("[MenuSifuTool] Step 4: Generating order")
            order_result = self._generate_order(
                calc_result, extracted_order, processed_items
            )
            if isinstance(order_result, str):
                return order_result  # Error message

            # Step 5: Format success response (database saving disabled for now)
            order_summary = extract_order_summary(order_result)

            success_message = f"""Order Successfully Placed!

**Order Details:**
• Order ID: {order_summary.get('order_id', 'N/A')}
• Order Number: {order_summary.get('order_number', 'N/A')}  
• Status: {order_summary.get('status', 'N/A')}
• Order Type: {order_summary.get('order_type', 'N/A')}

**Order Total:**
• Subtotal: ${order_summary.get('subtotal', 0):.2f}
• Tax: ${order_summary.get('tax_total', 0):.2f}
• Tips: ${order_summary.get('tips', 0):.2f}
• **Total: ${order_summary.get('total_amount', 0):.2f}**

**Customer Info:**
• Name: {order_summary.get('customer_name', 'N/A')}
• Email: {order_summary.get('customer_email', 'N/A')}

**Items Ordered:** {order_summary.get('item_count', 0)} items

Your order has been sent to the restaurant. Please wait for confirmation and pickup instructions."""

            return success_message

        except Exception as e:
            return f"Failed to process order checkout: {str(e)}"
