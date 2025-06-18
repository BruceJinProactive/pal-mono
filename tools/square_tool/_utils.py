from tools.square_tool.classes import CatalogItemObject, CatalogListResponse


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
