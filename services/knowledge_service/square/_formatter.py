"""
Square menu text formatting for knowledge base indexing.

This module handles the conversion of Square menu data into readable text
format suitable for vector indexing and natural language queries.

Key responsibilities:
- Generate readable text descriptions from menu items
- Format modifier information into natural language
- Create consolidated menu documents
- Handle price formatting and location-specific details

Text generation includes:
- Item names, descriptions, and prices
- Modifier groups and individual modifiers with pricing
- Category information when available
- Location-specific availability notes
"""

from typing import Any, Dict, List

from utils.log import logger


def generate_item_text(
    item: Dict[str, Any],
) -> str:
    """Generate readable text for a single menu item.

    Args:
        item: Menu item data dictionary

    Returns:
        str: Formatted text description of the menu item
    """
    text_parts = []

    # Item name and basic info
    item_name = item.get("name", "Unknown Item")
    text_parts.append(f"Menu Item: {item_name}")

    # Description - preserve full description without truncation
    if item.get("description"):
        description = item["description"]
        text_parts.append(f"Description: {description}")

    # Price
    if item.get("price"):
        text_parts.append(f"Price: {item['price']}")

    # No technical IDs in customer-facing version

    modifiers = item.get("modifiers", [])
    if modifiers:
        text_parts.append("Customization Options:")

        for mod_group in modifiers:
            group_name = mod_group.get("list_name", "Options")
            text_parts.append(f"  {group_name}:")

            group_modifiers = mod_group.get("modifiers", [])
            if group_modifiers:
                for modifier in group_modifiers:
                    mod_name = modifier.get("name", "Unknown Option")
                    price_info = modifier.get("price_info", "")
                    text_parts.append(f"    - {mod_name}{price_info}")
            else:
                text_parts.append("    - No options available")
    else:
        text_parts.append("No customization options available")

    # No technical IDs in customer-facing version
    return "\n".join(text_parts)


def format_consolidated_menu(
    menu_data: Dict[str, Any],
) -> Dict[str, str]:
    """Format complete menu data into consolidated text documents.

    Args:
        menu_data: Complete menu data from Square API

    Returns:
        dict: Mapping of document names to formatted text content
    """
    documents = {}

    menu_items = menu_data.get("menu_items", [])

    logger.debug(f"Formatting consolidated menu with {len(menu_items)} items")

    # Create main menu document
    doc_name = f"{menu_data.get('location_id')}_menu_{len(menu_items)}_items"
    menu_text_parts = []

    # Header - focus on item count and location info
    menu_text_parts.append(f"{len(menu_items)} Items")

    menu_text_parts.append("=" * 50)
    menu_text_parts.append("")

    # Process each menu item
    for i, item in enumerate(menu_items, 1):
        menu_text_parts.append(f"{i}. {item.get('name', 'Unknown Item')}")

        # Price
        if item.get("price"):
            menu_text_parts.append(f"   Price: {item['price']}")

        # Description - preserve full description without truncation
        if item.get("description"):
            description = item["description"]
            menu_text_parts.append(f"   Description: {description}")

        # No technical IDs in customer-facing consolidated menu

        # Modifier details - show all available options (no IDs)
        modifiers = item.get("modifiers", [])
        if modifiers:
            menu_text_parts.append("   Customization Options:")
            for mod_group in modifiers:
                group_name = mod_group.get("list_name", "Options")
                menu_text_parts.append(f"     {group_name}:")

                group_modifiers = mod_group.get("modifiers", [])
                if group_modifiers:
                    for modifier in group_modifiers:
                        mod_name = modifier.get("name", "Unknown Option")
                        price_info = modifier.get("price_info", "")
                        menu_text_parts.append(f"       - {mod_name}{price_info}")
                else:
                    menu_text_parts.append("       - No options available")
        else:
            menu_text_parts.append("   Customization: No options available")

        menu_text_parts.append("")

    # Add summary statistics
    menu_text_parts.append("MENU STATISTICS")
    menu_text_parts.append("-" * 30)

    # Count items with modifiers - follow test file structure
    items_with_modifiers = sum(1 for item in menu_items if item.get("modifiers"))
    items_without_modifiers = len(menu_items) - items_with_modifiers

    menu_text_parts.append(f"Items with customization options: {items_with_modifiers}")
    menu_text_parts.append(
        f"Items without customization options: {items_without_modifiers}"
    )

    # Count total modifiers
    total_modifier_groups = sum(len(item.get("modifiers", [])) for item in menu_items)
    total_modifiers = sum(
        sum(
            len(mod_group.get("modifiers", []))
            for mod_group in item.get("modifiers", [])
        )
        for item in menu_items
    )

    menu_text_parts.append(f"Total modifier groups: {total_modifier_groups}")
    menu_text_parts.append(f"Total modifier options: {total_modifiers}")

    documents[doc_name] = "\n".join(menu_text_parts)

    return documents


def format_item_categories(menu_items: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Organize menu items by categories for better organization.

    Args:
        menu_items: List of menu item dictionaries

    Returns:
        dict: Mapping of category names to lists of item names
    """
    categories = {}

    for item in menu_items:
        item_name = item.get("name", "Unknown Item")

        # Simple category detection based on item names
        # This is a basic implementation - could be enhanced with Square category data
        category = _detect_item_category(item_name)

        if category not in categories:
            categories[category] = []

        categories[category].append(item_name)

    return categories


def _detect_item_category(item_name: str) -> str:
    """Detect item category based on name patterns.

    Args:
        item_name: Name of the menu item

    Returns:
        str: Detected category name
    """
    item_lower = item_name.lower()

    # Tea categories
    if any(tea_term in item_lower for tea_term in ["tea", "chai", "matcha", "boba"]):
        return "Tea & Beverages"

    # Food categories
    if any(
        food_term in item_lower for food_term in ["toast", "sandwich", "bowl", "salad"]
    ):
        return "Food"

    # Dessert categories
    if any(
        dessert_term in item_lower
        for dessert_term in ["ice cream", "dessert", "sweet", "cake"]
    ):
        return "Desserts"

    # Coffee categories
    if any(
        coffee_term in item_lower
        for coffee_term in ["coffee", "latte", "cappuccino", "espresso"]
    ):
        return "Coffee"

    # Default category
    return "Other Items"


def format_pricing_summary(menu_items: List[Dict[str, Any]]) -> str:
    """Generate a pricing summary for the menu.

    Args:
        menu_items: List of menu item dictionaries

    Returns:
        str: Formatted pricing summary text
    """
    prices = []

    for item in menu_items:
        price_str = item.get("price", "")
        if price_str and "$" in price_str:
            try:
                # Extract numeric price (assuming format like "$12.50 USD")
                price_part = price_str.split("$")[1].split()[0]
                price_value = float(price_part)
                prices.append(price_value)
            except (ValueError, IndexError):
                continue

    if not prices:
        return "No pricing information available"

    summary_parts = []
    summary_parts.append("PRICING SUMMARY")
    summary_parts.append("-" * 20)
    summary_parts.append(f"Lowest price: ${min(prices):.2f}")
    summary_parts.append(f"Highest price: ${max(prices):.2f}")
    summary_parts.append(f"Average price: ${sum(prices) / len(prices):.2f}")
    summary_parts.append(f"Items with pricing: {len(prices)}")

    return "\n".join(summary_parts)
