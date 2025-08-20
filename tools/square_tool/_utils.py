import uuid
from typing import Any, Dict, List, Optional

from tools.square_tool._apis import create_order, get_catalog_object, list_catalog
from tools.square_tool.classes import (
    CatalogItemObject,
    CatalogListResponse,
    CreateOrderInput,
    Fulfillment,
    FulfillmentPickupDetails,
    FulfillmentRecipient,
    FulfillmentState,
    FulfillmentType,
    GetCatalogObjectInput,
    ListCatalogInput,
    Order,
    OrderLineItem,
    OrderLineItemModifier,
    SquareAccessToken,
)
from utils.log import logger


def _format_item_price(var_data) -> str:
    """Format price information for a menu item variation."""
    if var_data.price_money:
        price = var_data.price_money.amount / 100
        currency = var_data.price_money.currency
        size = var_data.name or "Regular"
        return f"   {size}: ${price:.2f} {currency}"
    return ""


def _format_dietary_info(food_details) -> list:
    """Format dietary information into a list of strings."""
    dietary_lines = []

    if food_details.calorie_count:
        dietary_lines.append(f"   {food_details.calorie_count} calories")

    if food_details.dietary_preferences:
        dietary_text = ", ".join(food_details.dietary_preferences)
        dietary_lines.append(f"   Dietary: {dietary_text}")

    if food_details.ingredients:
        ingredients_text = ", ".join(food_details.ingredients)
        dietary_lines.append(f"   Ingredients: {ingredients_text}")

    return dietary_lines


def _format_menu_item(item_obj: CatalogItemObject, item_number: int) -> list:
    """Format a single menu item into a list of strings."""
    lines = []

    # Basic item info
    name = item_obj.item_data.name or "Unnamed Item"
    description = item_obj.item_data.description or ""

    lines.append(f"{item_number}. {name}")

    if description:
        lines.append(f"   {description}")

    # Price information
    if (
        item_obj.item_data.variations
        and item_obj.item_data.variations[0].item_variation_data
    ):
        var_data = item_obj.item_data.variations[0].item_variation_data
        price_line = _format_item_price(var_data)
        if price_line:
            lines.append(price_line)

    # Alcohol warning
    if item_obj.item_data.is_alcoholic:
        lines.append("   Contains alcohol")

    # Dietary information
    if item_obj.item_data.food_and_beverage_details:
        dietary_lines = _format_dietary_info(
            item_obj.item_data.food_and_beverage_details
        )
        lines.extend(dietary_lines)

    lines.append("")  # Empty line after each item
    return lines


def extract_customer_menu(catalog_response: CatalogListResponse) -> str:
    """
    Extract customer-friendly menu information from Square catalog response.

    Args:
        catalog_response: CatalogListResponse from Square API

    Returns:
        str: Simple, customer-friendly menu text
    """
    if not catalog_response.objects:
        return "No menu items available."

    menu_lines = []
    menu_lines.append("MENU")
    menu_lines.append("=" * 20)
    menu_lines.append("")

    item_count = 0
    for obj in catalog_response.objects:
        if isinstance(obj, CatalogItemObject) and obj.item_data:
            item_count += 1
            item_lines = _format_menu_item(obj, item_count)
            menu_lines.extend(item_lines)

    if item_count == 0:
        return "No menu items found."

    menu_lines.append(f"Total items: {item_count}")

    return "\n".join(menu_lines)


def get_all_catalog_objects(access_token, use_production: bool):
    """
    Get all catalog objects using pagination.

    Args:
        access_token: Square API access token
        use_production: Whether to use production environment

    Returns:
        List of all catalog objects
    """
    all_catalog_objects = []
    cursor = None

    try:
        while True:
            input_data = ListCatalogInput(
                cursor=cursor,
                types=None,
                catalog_version=None,
                use_production=use_production,
            )

            catalog_response = list_catalog(
                access_token=access_token,
                input_data=input_data,
            )

            if catalog_response.objects:
                all_catalog_objects.extend(catalog_response.objects)

            # Check if there are more pages
            if hasattr(catalog_response, "cursor") and catalog_response.cursor:
                cursor = catalog_response.cursor
            else:
                break

        return all_catalog_objects

    except Exception as e:
        logger.error(f"[get_all_catalog_objects] Error: {e}")
        return []


def filter_location_available_items(
    catalog_objects: List[Any], location_id: str
) -> List[Dict[str, Any]]:
    """
    Filter catalog objects to get items available at the specified location.

    Args:
        catalog_objects: List of catalog objects from Square API
        location_id: Target location ID

    Returns:
        List of dictionaries containing item information
    """
    all_items = []

    for obj in catalog_objects:
        if obj.type == "ITEM" and isinstance(obj, CatalogItemObject):
            # Check if this item is available at our location
            present_at_all_locations = getattr(obj, "present_at_all_locations", False)
            present_at_location_ids = getattr(obj, "present_at_location_ids", []) or []
            absent_at_location_ids = getattr(obj, "absent_at_location_ids", []) or []

            # Apply location availability logic
            is_item_available = (
                present_at_all_locations and location_id not in absent_at_location_ids
            ) or location_id in present_at_location_ids

            if is_item_available:
                # Check if item should be excluded
                item_name = obj.item_data.name or ""
                is_curbside_item = "curbside pickup" in item_name.lower()
                has_ume_tag = "[ume]" in item_name.lower()

                if not is_curbside_item and not has_ume_tag:
                    # Get item price information
                    price_info = get_item_price_info(obj, location_id)

                    all_items.append(
                        {
                            "id": obj.id,
                            "name": obj.item_data.name or "Unnamed Item",
                            "description": getattr(obj.item_data, "description", None),
                            "price": price_info,
                        }
                    )

    return all_items


def get_item_price_info(item_obj: CatalogItemObject, location_id: str) -> str:
    """
    Extract price information for an item, including location-specific overrides.

    Args:
        item_obj: CatalogItemObject from Square API
        location_id: Target location ID

    Returns:
        Formatted price string
    """
    price_info = ""

    if hasattr(item_obj.item_data, "variations") and item_obj.item_data.variations:
        first_variation = item_obj.item_data.variations[0]
        if (
            hasattr(first_variation, "item_variation_data")
            and first_variation.item_variation_data
        ):
            var_data = first_variation.item_variation_data

            # First check for location-specific price overrides
            location_overrides = getattr(var_data, "location_overrides", []) or []
            location_price_found = False

            for override in location_overrides:
                if getattr(override, "location_id", None) == location_id:
                    if hasattr(override, "price_money") and override.price_money:
                        price = override.price_money.amount / 100
                        currency = getattr(override.price_money, "currency", "USD")
                        price_info = f"${price:.2f} {currency}"
                        location_price_found = True
                        break

            # If no location override found, use default price
            if (
                not location_price_found
                and hasattr(var_data, "price_money")
                and var_data.price_money
            ):
                price = var_data.price_money.amount / 100
                currency = getattr(var_data.price_money, "currency", "USD")
                price_info = f"${price:.2f} {currency}"

    return price_info


def get_detailed_catalog_object(access_token, object_id: str, use_production: bool):
    """
    Get detailed information about a specific catalog object.

    Args:
        access_token: Square API access token
        object_id: ID of the catalog object to retrieve
        use_production: Whether to use production environment

    Returns:
        Detailed catalog object response or None
    """
    try:
        get_input = GetCatalogObjectInput(
            object_id=object_id,
            catalog_version=None,
            include_related_objects=True,
            include_category_path_to_root=True,
            use_production=use_production,
        )

        object_response = get_catalog_object(access_token, get_input)
        return object_response

    except Exception as e:
        logger.error(
            f"[get_detailed_catalog_object] Error fetching object {object_id}: {e}"
        )
        return None


def _is_modifier_available_at_location(modifier_obj, location_id: str) -> bool:
    """Check if a modifier is available at the specified location."""
    present_at_all_locations = getattr(modifier_obj, "present_at_all_locations", False)
    present_at_location_ids = getattr(modifier_obj, "present_at_location_ids", []) or []
    absent_at_location_ids = getattr(modifier_obj, "absent_at_location_ids", []) or []

    return (
        present_at_all_locations and location_id not in absent_at_location_ids
    ) or location_id in present_at_location_ids


def _format_modifier_price(price_money) -> str:
    """Format modifier price information."""
    if not price_money:
        return ""

    price = price_money.amount / 100
    currency = getattr(price_money, "currency", "USD")

    if price > 0:
        return f" (+{currency} ${price:.2f})"
    elif price < 0:
        return f" (-{currency} ${abs(price):.2f})"
    return ""


def _find_modifier_list(related_objects, modifier_list_id: str):
    """Find a modifier list by ID in the related objects."""
    if not related_objects:
        return None

    for related_obj in related_objects:
        if related_obj.type == "MODIFIER_LIST" and related_obj.id == modifier_list_id:
            return getattr(related_obj, "modifier_list_data", None)

    return None


def _extract_location_modifiers(mod_list_data, location_id: str) -> Dict[str, Any]:
    """Extract modifiers from a modifier list that are available at the specified location."""
    if not mod_list_data:
        return {}

    modifiers = getattr(mod_list_data, "modifiers", None)
    if not modifiers or not isinstance(modifiers, (list, tuple)):
        return {}

    modifiers_info = []

    for modifier_obj in modifiers:
        if _is_modifier_available_at_location(modifier_obj, location_id):
            mod_data = getattr(modifier_obj, "modifier_data", None)
            if mod_data:
                price_info = _format_modifier_price(mod_data.price_money)

                modifiers_info.append(
                    {
                        "id": modifier_obj.id,
                        "name": mod_data.name,
                        "price_info": price_info,
                    }
                )

    # Only return modifier list info if there are available modifiers
    return (
        {
            "list_name": mod_list_data.name,
            "modifiers": modifiers_info,
        }
        if modifiers_info
        else {}
    )


def get_item_modifiers(detailed_response, location_id: str) -> List[Dict[str, Any]]:
    """
    Extract modifier information for an item, filtered by location availability.

    Args:
        detailed_response: Detailed catalog object response from Square API
        location_id: Target location ID

    Returns:
        List of modifier list dictionaries
    """
    if not detailed_response or not detailed_response.object:
        return []

    item_obj = detailed_response.object

    # Early return if not an item with modifier list info
    if (
        item_obj.type != "ITEM"
        or not isinstance(item_obj, CatalogItemObject)
        or not item_obj.item_data
        or not getattr(item_obj.item_data, "modifier_list_info", None)
    ):
        return []

    location_modifiers_for_item = []

    # Process each modifier list
    for mod_list_ref in item_obj.item_data.modifier_list_info:  # type: ignore
        modifier_list = _find_modifier_list(
            detailed_response.related_objects, mod_list_ref.modifier_list_id
        )

        if modifier_list:
            modifiers_info = _extract_location_modifiers(modifier_list, location_id)

            if modifiers_info:
                location_modifiers_for_item.append(modifiers_info)

    return location_modifiers_for_item


def _format_item_header(item_index: int, item: Dict[str, Any]) -> str:
    """Format the main item header line."""
    price_part = f" ({item['price']})" if item["price"] else ""
    return f"{item_index}. {item['name']}{price_part}"


def _format_item_details(item: Dict[str, Any], display_id: bool) -> List[str]:
    """Format item description and ID lines."""
    lines = []

    if item.get("description"):
        lines.append(f"*Description: {item['description']}")

    if display_id and item.get("id"):
        lines.append(f"*Item ID: {item['id']}")

    return lines


def _format_modifiers_section(
    modifiers: List[Dict[str, Any]], display_id: bool
) -> List[str]:
    """Format the modifiers section for an item."""
    if not modifiers:
        return ["*No modifiers available for this item"]

    lines = ["*Available Modifiers:"]

    for mod_list in modifiers:
        if mod_list.get("list_name") and mod_list.get("modifiers"):
            lines.append(f"**{mod_list['list_name']}:")

            for modifier in mod_list["modifiers"]:
                modifier_name = modifier.get("name", "Unknown Modifier")
                modifier_price = modifier.get("price_info", "")
                lines.append(f"***{modifier_name}{modifier_price}")

                if display_id and modifier.get("id"):
                    lines.append(f"****Modifier ID: {modifier['id']}")

    return lines


def _format_menu_header(item_count: int) -> List[str]:
    """Format the menu header section."""
    return ["COMPLETE MENU", "=" * 50, f"Available Items: {item_count}", ""]


def _format_menu_footer(menu_items: List[Dict[str, Any]]) -> List[str]:
    """Format the menu footer with summary statistics."""
    # Count total modifiers
    total_modifiers = 0
    for item in menu_items:
        for mod_list in item.get("location_modifiers", []):
            total_modifiers += len(mod_list.get("modifiers", []))

    return [
        "=" * 50,
        f"Total Menu Items: {len(menu_items)}",
        f"Total Available Modifiers: {total_modifiers}",
        "=" * 50,
    ]


def format_customer_menu(
    menu_items: List[Dict[str, Any]], display_id: bool = False
) -> str:
    """
    Format the final menu for customer display with complete information.

    Args:
        menu_items: List of menu item dictionaries with details
        display_id: Whether to display item and modifier IDs (default: False)

    Returns:
        Formatted menu string with complete information and asterisk-based hierarchy
    """
    if not menu_items:
        return "No menu items are currently available at this location."

    menu_content = []

    # Add header
    menu_content.extend(_format_menu_header(len(menu_items)))

    # Format each menu item
    for item_index, item in enumerate(menu_items, 1):
        # Format item header
        menu_content.append(_format_item_header(item_index, item))

        # Format item details
        menu_content.extend(_format_item_details(item, display_id))

        # Format modifiers
        modifiers = item.get("location_modifiers", [])
        menu_content.extend(_format_modifiers_section(modifiers, display_id))

        # Add separator between items
        menu_content.append("")

    # Add footer
    menu_content.extend(_format_menu_footer(menu_items))

    return "\n".join(menu_content)


def create_comprehensive_menu(
    access_token, location_id: str, use_production: bool, display_id: bool = False
) -> str:
    """
    Create a comprehensive customer menu using all the utility functions.

    Args:
        access_token: Square API access token
        location_id: Target location ID
        use_production: Whether to use production environment
        display_id: Whether to display item and modifier IDs (default: False)

    Returns:
        Formatted comprehensive menu string
    """
    try:
        # Step 1: Get all catalog objects
        all_catalog_objects = get_all_catalog_objects(access_token, use_production)
        if not all_catalog_objects:
            return "Unable to retrieve catalog information."

        # Step 2: Filter items available at this location
        available_items = filter_location_available_items(
            all_catalog_objects, location_id
        )
        if not available_items:
            return "No menu items are currently available at this location."

        # Step 3: Get detailed information and modifiers for each item
        final_menu = []
        for item in available_items:
            detailed_response = get_detailed_catalog_object(
                access_token, item["id"], use_production
            )
            location_modifiers = get_item_modifiers(detailed_response, location_id)

            # Add modifiers to item
            item["location_modifiers"] = location_modifiers
            final_menu.append(item)

        # Step 4: Format the menu for display
        return format_customer_menu(final_menu, display_id=display_id)

    except Exception as e:
        logger.error(f"[create_comprehensive_menu] Error: {e}")
        return "Failed to create menu. Please try again."


def get_item_variation_id(
    access_token: SquareAccessToken, item_id: str, use_production: bool
) -> Optional[str]:
    """Get the first variation ID for an item."""
    try:
        get_input = GetCatalogObjectInput(
            object_id=item_id,
            catalog_version=None,
            include_related_objects=True,
            include_category_path_to_root=True,
            use_production=use_production,
        )

        response = get_catalog_object(access_token, get_input)

        if not response or not response.object:
            logger.error(
                f"[get_item_variation_id] Could not fetch item details for {item_id}"
            )
            return None

        item_obj = response.object

        # Check if it's an item object
        if not isinstance(item_obj, CatalogItemObject) or not item_obj.item_data:
            logger.error(
                f"[get_item_variation_id] Object {item_id} is not a valid item"
            )
            return None

        # Get variation (use first one)
        if not item_obj.item_data.variations:
            logger.error(f"[get_item_variation_id] Item {item_id} has no variations")
            return None

        variation = item_obj.item_data.variations[0]
        return variation.id

    except Exception as e:
        logger.error(
            f"[get_item_variation_id] Error getting variation for item {item_id}: {e}"
        )
        return None


def _create_line_item_modifiers(
    modifiers: List[Dict[str, Any]],
) -> List[OrderLineItemModifier]:
    """Create line item modifiers from modifier data."""
    line_item_modifiers = []
    for modifier in modifiers:
        modifier_obj = OrderLineItemModifier(
            uid=str(uuid.uuid4())[:8],
            catalog_object_id=modifier["modifier_id"],
            name=modifier["modifier_name"],
            quantity="1",
        )
        line_item_modifiers.append(modifier_obj)
    return line_item_modifiers


def _create_order_line_item(
    item_name: str,
    quantity: int,
    variation_id: str,
    modifiers: List[Dict[str, Any]],
    special_notes: Optional[str],
) -> OrderLineItem:
    """Create a single order line item."""
    line_item_modifiers = _create_line_item_modifiers(modifiers)

    palona_note = "Palona AI - Order created via automated system"
    combined_note = f"{palona_note} | {special_notes}" if special_notes else palona_note

    return OrderLineItem(
        uid=str(uuid.uuid4())[:8],
        catalog_object_id=variation_id,
        name=item_name,
        quantity=str(quantity),
        note=combined_note,
        variation_name=None,
        modifiers=line_item_modifiers if line_item_modifiers else None,
    )


def create_square_order_with_modifiers(
    access_token: SquareAccessToken,
    location_id: str,
    matched_items: List[Dict[str, Any]],
    use_production: bool,
    customer_name: Optional[str] = None,
    phone_number: Optional[str] = None,
) -> Optional[Order]:
    """Create Square order with modifiers support."""
    try:
        line_items = []

        for item_dict in matched_items:
            line_item = _create_order_line_item(
                item_dict["item_name"],
                item_dict["quantity"],
                item_dict["variation_id"],
                item_dict["modifiers"],
                item_dict.get("special_notes"),
            )

            line_items.append(line_item)
            logger.info(
                f"[create_square_order_with_modifiers] Created line item for {item_dict['item_name']} "
            )

        if not line_items:
            logger.error(
                "[create_square_order_with_modifiers] No valid line items created"
            )
            return None

        # Create fulfillment with customer name and phone if provided
        fulfillments = None
        # Add +1 country code to phone number for fulfillment (phone_number should be in 555-555-5555 format from extraction)
        if phone_number:
            # Add +1 country code if not already present
            if not phone_number.startswith("+"):
                phone_number = f"+1{phone_number}"

        # Create recipient with customer name and formatted phone number
        recipient = FulfillmentRecipient(
            display_name=customer_name, phone_number=phone_number
        )

        # Create pickup details with recipient
        pickup_details = FulfillmentPickupDetails(
            recipient=recipient,
            schedule_type="ASAP",
            note=f"Order for {customer_name}",
        )

        # Create fulfillment - only set non-read-only fields
        fulfillment = Fulfillment(
            uid=str(uuid.uuid4())[:8],
            type=FulfillmentType.PICKUP,
            state=FulfillmentState.PROPOSED,
            pickup_details=pickup_details,
        )

        fulfillments = [fulfillment]
        logger.info(
            f"[create_square_order_with_modifiers] Created fulfillment for customer: {customer_name}"
        )

        # Create order
        order = Order(
            location_id=location_id,
            reference_id=None,
            customer_id=None,
            ticket_name=None,
            line_items=line_items,
            fulfillments=fulfillments,
            metadata={"palona_testing": "Order created via Palona AI automated system"},
        )

        # Generate unique idempotency key
        idempotency_key = str(uuid.uuid4())

        create_order_input = CreateOrderInput(
            order=order,
            idempotency_key=idempotency_key,
            use_production=use_production,
        )

        # Create the order
        order_response = create_order(access_token, create_order_input)

        if order_response.errors:
            logger.error(
                f"[create_square_order_with_modifiers] Order creation failed: {order_response.errors}"
            )
            return None

        if not order_response.order:
            logger.error(
                "[create_square_order_with_modifiers] No order returned from Square API"
            )
            return None

        logger.info(
            f"[create_square_order_with_modifiers] Order created successfully: {order_response.order.id}"
        )
        return order_response.order

    except Exception as e:
        logger.error(f"[create_square_order_with_modifiers] Error: {e}")
        return None


def format_money(money_obj) -> str:
    """Format money object to readable string"""
    if not money_obj or not hasattr(money_obj, "amount"):
        return "$0.00"
    amount_cents = money_obj.amount
    return f"${amount_cents/100:.2f}"


def get_line_item_pricing(line_item, item_name: str) -> tuple[str, List[str]]:
    """Extract pricing information from a line item.

    Returns:
        tuple: (line_item_price, modifier_details_list)
    """
    line_item_price = "$0.00"
    modifier_details = []

    if line_item.name != item_name:
        return line_item_price, modifier_details

    # Get total price for the line item
    if hasattr(line_item, "total_money") and line_item.total_money:
        line_item_price = format_money(line_item.total_money)

    # Get modifier details with prices
    if line_item.modifiers:
        for line_mod in line_item.modifiers:
            mod_price = "$0.00"
            if hasattr(line_mod, "total_price_money") and line_mod.total_price_money:
                mod_price = format_money(line_mod.total_price_money)
            elif hasattr(line_mod, "base_price_money") and line_mod.base_price_money:
                mod_price = format_money(line_mod.base_price_money)

            price_display = f" (+{mod_price})" if mod_price != "$0.00" else ""
            modifier_details.append(f"{line_mod.name}{price_display}")

    return line_item_price, modifier_details


def format_item_details(
    matched_items: List[Dict[str, Any]], created_order
) -> List[str]:
    """Format item details with pricing for order success message.

    Args:
        matched_items: List of matched items from catalog
        created_order: The created Square order object

    Returns:
        List of formatted item detail strings
    """
    item_details = []

    for item in matched_items:
        item_name = item["item_name"]
        quantity = item["quantity"]

        # Find corresponding line item for pricing
        line_item_price = "$0.00"
        modifier_details = []

        if created_order.line_items:
            for line_item in created_order.line_items:
                if line_item.name == item_name:
                    line_item_price, modifier_details = get_line_item_pricing(
                        line_item, item_name
                    )
                    break

        # Format item text with pricing
        item_text = f"• {quantity}x {item_name} - {line_item_price}"
        if modifier_details:
            item_text += f"\n  Modifiers: {', '.join(modifier_details)}"

        item_details.append(item_text)

    return item_details


def format_order_totals(created_order) -> str:
    """Format order total information including tax.

    Args:
        created_order: The created Square order object

    Returns:
        Formatted order totals string
    """
    order_total_text = ""

    if hasattr(created_order, "total_money") and created_order.total_money:
        order_total = format_money(created_order.total_money)
        order_total_text = f"\nOrder Total: {order_total}"

        # Add tax information if available
        if (
            hasattr(created_order, "total_tax_money")
            and created_order.total_tax_money
            and created_order.total_tax_money.amount > 0
        ):
            tax_amount = format_money(created_order.total_tax_money)
            order_total_text += f"\nTax: {tax_amount}"

    return order_total_text


def format_order_success_message(
    created_order,
    location_id: str,
    matched_items: List[Dict[str, Any]],
    payment_url: str,
    missing_items: Optional[List[str]] = None,
) -> str:
    """Format the complete order success message.

    Args:
        created_order: The created Square order object
        location_id: Square location ID
        matched_items: List of matched items from catalog
        payment_url: Payment link URL
        missing_items: List of items that couldn't be found (optional)

    Returns:
        Formatted success message string
    """
    # Calculate total quantity
    total_quantity = sum(item["quantity"] for item in matched_items)

    # Format item details
    item_details = format_item_details(matched_items, created_order)
    items_text = "\n".join(item_details)

    # Format order totals
    order_total_text = format_order_totals(created_order)

    # Extract customer name and phone from fulfillment if available
    customer_info = ""
    if created_order.fulfillments:
        for fulfillment in created_order.fulfillments:
            if (
                fulfillment.pickup_details
                and fulfillment.pickup_details.recipient
                and fulfillment.pickup_details.recipient.display_name
            ):
                customer_name = fulfillment.pickup_details.recipient.display_name
                phone_number = fulfillment.pickup_details.recipient.phone_number

                customer_info = f"\nCustomer: {customer_name}"
                if phone_number:
                    customer_info += f"\nPhone: {phone_number}"
                break

    # Create the main success message
    success_message = f"""Order created successfully!
Order ID: {created_order.id}
Location: {location_id}{customer_info}

Items ({total_quantity} items total):
{items_text}{order_total_text}

Payment Link: {payment_url}
Status: Ready for payment"""

    # Add warning about missing items if any
    if missing_items:
        missing_text = ", ".join(missing_items)
        success_message += f"\n\nNote: The following items could not be found in the catalog and were not added to the order: {missing_text}"

    return success_message
