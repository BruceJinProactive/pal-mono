"""
MenuSifu Tool implementation for online ordering and checkout
"""

import json
from decimal import Decimal
from typing import Dict, List, Optional, Union

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
    convert_extracted_order_to_dict,
    extract_order_summary,
    safe_convert_item_fields,
    safe_convert_option_fields,
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
        namespace: str,
        index_name: str,
        tool_metadata: ToolMetadata,
        base_url: str = "assistant.mealkeyway.com",
        merchant_id: Optional[str] = None,
        access_token: Optional[str] = None,
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
        self.access_token = access_token
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

    def _resolve_payment_method(self, pm_input) -> tuple[PaymentMethod, bool]:
        """
        Resolve various payment method inputs to PaymentMethod enum and pay_online flag.

        Args:
            pm_input: PaymentMethod enum, int, or string (including synonyms and numerics)

        Returns:
            tuple: (PaymentMethod, bool) - payment method and whether it's online payment
        """
        # Accept PaymentMethod, int, or string (incl. synonyms and numerics).
        if isinstance(pm_input, PaymentMethod):
            method = pm_input
        elif isinstance(pm_input, int):
            method = (
                PaymentMethod(pm_input)
                if pm_input in {e.value for e in PaymentMethod}
                else PaymentMethod.CASH
            )
        elif isinstance(pm_input, str):
            s = pm_input.strip().lower()
            map_ = {
                "credit": PaymentMethod.CREDIT_CARD,
                "card": PaymentMethod.CREDIT_CARD,
                "credit card": PaymentMethod.CREDIT_CARD,
                "wechat": PaymentMethod.WECHAT_PAY,
                "wechat pay": PaymentMethod.WECHAT_PAY,
                "wechatpay": PaymentMethod.WECHAT_PAY,
                "微信": PaymentMethod.WECHAT_PAY,
                "cash": PaymentMethod.CASH,
                "pay on pickup": PaymentMethod.CASH,
                "pay on delivery": PaymentMethod.CASH,
                "现金": PaymentMethod.CASH,
            }
            if s.isdigit() and int(s) in {1, 7, 8}:
                method = PaymentMethod(int(s))
            else:
                method = map_.get(s, PaymentMethod.CASH)
        else:
            method = PaymentMethod.CASH
        pay_online = method in {PaymentMethod.CREDIT_CARD, PaymentMethod.WECHAT_PAY}
        return method, pay_online

    @property
    def _menusifu_token(self) -> tuple[str, str]:
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
            merchant_id = get_client_secret_with_fallback("MENUSIFU_MERCHANT_ID")
            if not access_token:
                logger.error("No MenuSifu access token found in secret manager")
                raise ValueError(
                    "MenuSifu access token is required - check MENUSIFU_ACCESS_TOKEN secret"
                )

            return access_token, merchant_id
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

            # Schema enforces required first name; rely on ValidationError path for consistent messages.

            # Validate phone object before using it later in the flow
            if not extracted_order.customer_phone:
                return "Customer phone number is required for order processing. Please provide phone number in the conversation."

            # Trim phone number before validating emptiness
            if extracted_order.customer_phone.number:
                extracted_order.customer_phone.number = (
                    extracted_order.customer_phone.number.strip()
                )
            if not extracted_order.customer_phone.number:
                return "Customer phone number is required for order processing. Please provide a valid phone number in the conversation."

            # Default missing country code to +1 per prompt rules
            if not extracted_order.customer_phone.country_code:
                extracted_order.customer_phone.country_code = "+1"  # per prompt default
                logger.info("Defaulted missing phone country code to +1.")

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
            logger.warning(
                f"[MenuSifuTool] Order extraction returned error: {extracted_order}"
            )
            return extracted_order

        logger.info(
            f"[MenuSifuTool] Successfully extracted order with {len(extracted_order.items)} items for customer: {extracted_order.customer_first_name}"
        )

        # Log detailed extracted order information
        logger.info("[MenuSifuTool] Extracted Order Details:")
        logger.info(
            f"  - Customer: {extracted_order.customer_first_name} {extracted_order.customer_last_name or ''}"
        )
        logger.info(
            f"  - Phone: {extracted_order.customer_phone.country_code}{extracted_order.customer_phone.number}"
        )
        logger.info(f"  - Order Type: {extracted_order.order_type}")
        logger.info(
            f"  - Payment Method: {extracted_order.payment_method} (value: {extracted_order.payment_method.value})"
        )

        for i, item in enumerate(extracted_order.items, 1):
            logger.info(f"  - Item {i}: {item.item_name} (ID: {item.item_id})")
            logger.info(
                f"    * Price: ${item.price}, Display: {item.display_price}, Qty: {item.quantity}"
            )
            logger.info(f"    * Type: {item.item_type}, Category: {item.category_id}")
            if item.modifiers:
                logger.info(f"    * Modifiers: {len(item.modifiers)} items")
                for mod in item.modifiers:
                    logger.debug(
                        f"      - {mod.name}: ${mod.price} (qty: {mod.quantity})"
                    )

        # Convert ExtractedMenuSifuOrder to internal dict format
        processed_items = convert_extracted_order_to_dict(extracted_order)
        logger.debug(
            f"[MenuSifuTool] Converted {len(processed_items)} items to internal dict format"
        )

        # Log converted items details
        logger.debug("[MenuSifuTool] Converted Items Details:")
        for i, item in enumerate(processed_items, 1):
            logger.debug(f"  - Converted Item {i}: {item.get('name')}")
            logger.debug(
                f"    * ID: {item.get('id')}, Sale ID: {item.get('sale_item_id')}"
            )
            logger.debug(
                f"    * Price: {item.get('price')}, Display: {item.get('display_price')}"
            )
            logger.debug(
                f"    * Type: {item.get('item_type')}, Category: {item.get('category_id')}"
            )
            logger.debug(f"    * Options: {len(item.get('options', []))}")

        return processed_items

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
            logger.debug(
                f"[MenuSifuTool] Starting order total calculation for {len(order_items)} items"
            )

            # Always use pickup order type (delivery not supported)
            # Validate that order_items is non-empty
            if not order_items:
                logger.error(
                    "[MenuSifuTool] Cannot calculate order total: no items provided"
                )
                return "Cannot calculate order total: no items provided"

            # Convert order_items to OrderSelectedItem instances
            selected_items = []
            logger.debug("[MenuSifuTool] Converting items to OrderSelectedItem format")
            for i, item in enumerate(order_items, 1):
                try:
                    logger.debug(
                        f"[MenuSifuTool] Processing item {i}: {item.get('name', 'Unknown')}"
                    )

                    # Use helper function for safe field conversion
                    safe_fields = safe_convert_item_fields(item)

                    # Log safe field conversion results
                    logger.debug(f"[MenuSifuTool] Safe field conversion for item {i}:")
                    logger.debug(f"  - Raw item: {item}")
                    logger.debug(f"  - Safe fields: {safe_fields}")

                    # Convert price (Decimal) to displayPrice (int) - same value, different type
                    price_decimal = safe_fields["price"]
                    display_price_int = int(price_decimal) if price_decimal else None

                    logger.debug(
                        f"[MenuSifuTool] Price conversion: {price_decimal} (Decimal) -> {display_price_int} (int)"
                    )

                    # Map fields from order_items to OrderSelectedItem format
                    selected_item = OrderSelectedItem(
                        categoryId=safe_fields["categoryId"],
                        displayPrice=display_price_int,  # Same as price but as int
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

                    # Log final OrderSelectedItem details in one line
                    logger.info(
                        f"[MenuSifuTool] Created OrderSelectedItem {i}: {selected_item.name} (ID: {selected_item.id}, Price: ${selected_item.price}, Display: {selected_item.display_price}, Qty: {selected_item.quantity}, Category: {selected_item.category_id}, Type: {selected_item.item_type}, Options: {len(selected_item.options or [])})"
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

            # Log calculation request details
            logger.info("[MenuSifuTool] Order Calculation Request:")
            logger.info(f"  - Order Type: {calc_request.order_type}")
            logger.info(
                f"  - Payment Method: {calc_request.payment_method} (value: {calc_request.payment_method.value})"
            )
            logger.info(f"  - Total Tips: ${calc_request.total_tips}")
            logger.info(f"  - Delivery Fee: ${calc_request.delivery_fee}")
            logger.info(f"  - Selected Items: {len(calc_request.selected_items)}")

            # Log the JSON payload (debug level)
            logger.debug("[MenuSifuTool] Calculation API JSON payload:")
            logger.debug(f"  {calc_request.model_dump_json(by_alias=True)}")

            # Call calculation API
            logger.info(
                f"[MenuSifuTool] Calling MenuSifu order calculation API with {len(selected_items)} items"
            )
            calc_result = calculate_order_total(
                access_token=self.access_token or self._menusifu_token[0],
                merchant_id=self.merchant_id or self._menusifu_token[1],
                order_request=calc_request,
                base_url=self.base_url,
            )

            # Return OrderCalculationResponse directly, or convert error response to string
            if isinstance(calc_result, OrderCalculationResponse):
                subtotal = getattr(calc_result, "order_subtotal", "N/A")
                total = getattr(calc_result, "order_total", "N/A")
                tax_total = getattr(calc_result, "order_tax_total", "N/A")

                logger.info(
                    f"[MenuSifuTool] Order calculation successful - subtotal: ${subtotal}"
                )

                # Log detailed calculation response
                logger.info("[MenuSifuTool] Order Calculation Response Details:")
                logger.info(f"  - Subtotal: ${subtotal}")
                logger.info(f"  - Tax Total: ${tax_total}")
                logger.info(f"  - Order Total: ${total}")
                logger.info(
                    f"  - Discount: ${getattr(calc_result, 'order_discount', 'N/A')}"
                )
                logger.info(
                    f"  - Charge: ${getattr(calc_result, 'order_charge', 'N/A')}"
                )
                logger.info(
                    f"  - Tips: ${getattr(calc_result, 'order_total_tips', 'N/A')}"
                )

                # Log charge objects details
                charge_obj = getattr(calc_result, "charge_obj", [])
                logger.debug(f"[MenuSifuTool] Charge objects: {len(charge_obj)} items")
                for i, charge in enumerate(charge_obj):
                    logger.debug(
                        f"  - Charge {i+1}: ${charge.charge} (type: {getattr(charge, 'type', 'N/A')})"
                    )

                return calc_result
            else:
                logger.warning(
                    f"[MenuSifuTool] Order calculation returned error: {calc_result}"
                )
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
            logger.debug(
                f"[MenuSifuTool] Starting order generation for {len(order_items)} items"
            )

            # Always use pickup order type (delivery not supported)
            # Validate that order_items is non-empty
            if not order_items:
                logger.error("[MenuSifuTool] Cannot generate order: no items provided")
                return "Cannot generate order: no items provided"

            # Handle error case where customer_info is an error string
            if isinstance(customer_info, str):
                logger.warning(
                    f"[MenuSifuTool] Order generation aborted due to customer info error: {customer_info}"
                )
                return customer_info

            # Extract customer info directly from the unified extraction result
            # At this point, customer_info must be ExtractedMenuSifuOrder (str case handled above)
            customer_email = customer_info.customer_email or "test@palona.com"
            customer_first_name = customer_info.customer_first_name
            customer_last_name = customer_info.customer_last_name

            # Log order processing without exposing PII at info level
            logger.info(
                "[MenuSifuTool] Processing order for customer - validation passed"
            )
            # Log PII details only at debug level for troubleshooting
            logger.debug(
                f"[MenuSifuTool] Customer details: {customer_first_name} {customer_last_name or ''} ({customer_email})"
            )

            # Handle phone information from structured Phone object (required)
            # Safe access with validation (validated earlier in extraction)
            if not customer_info.customer_phone:
                logger.error(
                    "[MenuSifuTool] Customer phone information is missing from extracted order"
                )
                return "Customer phone information is missing from extracted order"

            country_code = customer_info.customer_phone.country_code
            phone_number = customer_info.customer_phone.number

            # Additional safety check
            if not country_code or not phone_number:
                return "Customer phone number or country code is missing from extracted order"
            payment_method_str = "CASH"  # Hardcoded to cash as requested
            logger.debug(f"[MenuSifuTool] Using payment method: {payment_method_str}")
            # Address fields not needed for pickup orders

            # Validate that normalized phone_number is non-empty
            if not phone_number or phone_number.strip() == "":
                full_name = f"{customer_first_name} {customer_last_name or ''}".strip()
                return f"Customer phone number is required for order processing. Customer: {full_name} ({customer_email})"

            # Build customer using helper function
            customer = build_customer_info(
                email=customer_email,
                first_name=customer_first_name,
                last_name=customer_last_name or "",  # Handle optional None last_name
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
                    safe_fields = safe_convert_item_fields(item)

                    # Convert options/modifiers to OrderItemOptionNote using helper
                    item_options = []
                    if item.get("options"):
                        for option in item["options"]:
                            safe_option_fields = safe_convert_option_fields(option)

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

            # Log order generation request details
            logger.info("[MenuSifuTool] Order Generation Request:")
            logger.info(
                f"  - Customer: {order_request.customer.first_name} {order_request.customer.last_name}"
            )
            logger.info(
                f"  - Phone: {order_request.country_code}{order_request.telephone_number}"
            )
            logger.info(f"  - Channel: {order_request.channel}")
            logger.info(f"  - Order Type: {order_request.order_type}")
            logger.info(
                f"  - Payment Method: {order_request.payment_method} (value: {order_request.payment_method.value})"
            )
            logger.info(f"  - Pay Online: {order_request.pay_online}")
            logger.info(f"  - Selected Items: {len(order_request.selected_items)}")
            logger.info(f"  - Total Price: ${order_request.price.total}")
            logger.info(f"  - Subtotal: ${order_request.price.subtotal}")
            logger.info(f"  - Tax Total: ${order_request.price.tax_total}")

            # Log generation request JSON payload (debug level)
            logger.debug("[MenuSifuTool] Generation API JSON payload:")
            logger.debug(f"  {order_request.model_dump_json(by_alias=True)}")

            # Call order generation API
            logger.info(
                f"[MenuSifuTool] Calling MenuSifu order generation API for customer: {customer_first_name}"
            )
            logger.debug(
                f"[MenuSifuTool] Order details: {len(selected_items)} items, payment: {payment_method}"
            )

            order_result = generate_order(
                access_token=self.access_token or self._menusifu_token[0],
                merchant_id=self.merchant_id or self._menusifu_token[1],
                order_request=order_request,
                base_url=self.base_url,
            )

            if isinstance(order_result, OrderGenerationResponse):
                # Safely extract order ID from nested order object
                order_obj = getattr(order_result, "order", None)
                if order_obj:
                    # Try order._id (alias order_id) first, then order_number as fallback
                    order_id = getattr(order_obj, "_id", None) or getattr(
                        order_obj, "order_number", "N/A"
                    )
                    order_number = getattr(order_obj, "order_number", "N/A")
                    status = getattr(order_obj, "status", "N/A")

                    # Log detailed order generation response
                    logger.info("[MenuSifuTool] Order Generation Response Details:")
                    logger.info(f"  - Order ID: {order_id}")
                    logger.info(f"  - Order Number: {order_number}")
                    logger.info(f"  - Status: {status}")

                    # Log price details from the generated order
                    order_price = getattr(order_obj, "price", None)
                    if order_price:
                        logger.info(
                            f"  - Final Total: ${getattr(order_price, 'total', 'N/A')}"
                        )
                        logger.info(
                            f"  - Final Subtotal: ${getattr(order_price, 'subtotal', 'N/A')}"
                        )
                        logger.info(
                            f"  - Final Tax: ${getattr(order_price, 'tax_total', 'N/A')}"
                        )

                    logger.info(
                        f"  - Customer: {getattr(order_obj, 'customer_name', 'N/A')}"
                    )
                    logger.info(
                        f"  - Phone: {getattr(order_obj, 'customer_phone', 'N/A')}"
                    )

                else:
                    order_id = "N/A"
                    logger.warning("[MenuSifuTool] Order object missing from response")

                logger.info(
                    f"[MenuSifuTool] Order generation successful - Order ID: {order_id}"
                )
            else:
                logger.error(f"[MenuSifuTool] Order generation failed: {order_result}")

            # Return result directly - it's either OrderGenerationResponse or error string
            return order_result

        except Exception as e:
            logger.error(f"[MenuSifuTool] Order generation exception: {str(e)}")
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

        Args:
            customer_name: Customer's full name for the order.
            phone_number: Customer's phone number for order pickup.

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
            logger.info("[MenuSifuTool] Step 5: Formatting success response")
            order_summary = extract_order_summary(order_result)
            order_id = order_summary.get("order_id", "N/A")
            logger.info(
                f"[MenuSifuTool] Order checkout completed successfully - Final Order ID: {order_id}"
            )

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
            logger.error(
                f"[MenuSifuTool] Order checkout process failed with exception: {str(e)}"
            )
            return f"Failed to process order checkout: {str(e)}"
