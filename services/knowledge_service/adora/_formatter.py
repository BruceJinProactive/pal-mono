"""
Menu text formatting and generation for Adora integration.

This module converts structured menu data into human-readable text formats
suitable for knowledge base indexing and customer-facing display.

Key responsibilities:
- Generate formatted text from menu item dictionaries
- Create consistent markdown-style menu representations
- Format consolidated menu views grouped by category
- Handle both ID-inclusive and clean display formats

Output formats:
- Individual menu items with prices, descriptions, and modifiers
- Consolidated menu overviews organized by category
- Clean, readable text optimized for AI processing
"""

from collections import defaultdict
from typing import Any, Dict, List

from ._utils import get_category_name, get_modifier_group_name, get_size_description


def generate_item_text(
    item: Dict[str, Any],
    menu_data: Dict[str, Any],
    with_ids: bool = False,
) -> str:
    """Generate text representation of a menu item.

    Args:
        item: The menu item dictionary
        menu_data: The complete menu data dictionary
        with_ids: Whether to include IDs in the output

    Returns:
        str: Formatted text representation of the menu item
    """
    categories = menu_data.get("categories", [])
    sizes = menu_data.get("sizes", [])
    global_modifier_groups = menu_data.get("modifier_groups", [])

    # Create modifiers lookup
    modifiers = {}
    for modifier in menu_data.get("modifiers", []):
        modifier_id = modifier["modifier_id"]
        modifiers[modifier_id] = modifier["name"]

    item_id = item.get("item_id")
    item_name = item.get("name", f"Item {item_id}")
    item_category_id = item.get("item_category_id")
    category_name = get_category_name(categories, item_category_id or "")
    description = item.get("description", "")

    lines = []

    # Title
    if with_ids:
        lines.append(f"# {item_name} (item_id: {item_id})")
    else:
        lines.append(f"# {item_name}")

    lines.extend(
        [
            "",
            f"**Category:** {category_name}",
            "",
            f"**Description:** {description}",
            "",
        ]
    )

    # Get allowed sizes
    order_types = item.get("order_types", [])
    allowed_size_ids = set()
    if order_types:
        for order_type in order_types:
            for size in order_type.get("sizes", []):
                size_id = size.get("size_id")
                if size_id:
                    allowed_size_ids.add(size_id)

    # Prices section
    prices = item.get("prices", [])
    visible_prices = [
        p
        for p in prices
        if not allowed_size_ids or p.get("size_id") in allowed_size_ids
    ]
    if visible_prices:
        lines.append("## Prices")
        for p in visible_prices:
            size_id = p.get("size_id")
            price = p.get("price")
            size_desc = get_size_description(sizes, size_id)
            if with_ids:
                lines.append(f"- {size_desc} (size_id: {size_id}): ${price}")
            else:
                lines.append(f"- {size_desc}: ${price}")
        lines.append("")
    else:
        # Throw error if no visible prices are available
        raise ValueError(
            f"No visible prices found for item '{item_name}' (item_id: {item_id}). "
            f"Raw prices: {prices}, Allowed size IDs: {allowed_size_ids}"
        )

    # Modifiers section
    modifier_groups_item = item.get("modifier_groups", [])
    if modifier_groups_item:
        lines.append("## Modifiers")
        for group in modifier_groups_item:
            group_id = group.get("modifier_group_id")
            group_name = get_modifier_group_name(global_modifier_groups, group_id)
            lines.append(f"### {group_name}")

            # Separate included and optional modifiers
            included = []
            optional = []
            for mod in group.get("modifiers", []):
                if mod.get("default"):
                    included.append(mod)
                else:
                    optional.append(mod)

            if included:
                lines.append("#### Included in the price")
                for mod in included:
                    modifier_name = modifiers.get(mod.get("modifier_id"), "Unknown")
                    if with_ids:
                        lines.append(
                            f"- {modifier_name} (modifier_id: {mod.get('modifier_id')})"
                        )
                    else:
                        lines.append(f"- {modifier_name}")

            if optional:
                lines.append("#### Optional (add-on)")
                for mod in optional:
                    modifier_name = modifiers.get(mod.get("modifier_id"), "Unknown")
                    if with_ids:
                        lines.append(
                            f"- {modifier_name} (modifier_id: {mod.get('modifier_id')})"
                        )
                    else:
                        lines.append(f"- {modifier_name}")

            lines.append("")

    return "\n".join(lines)


def format_consolidated_menu(menu_items: List[Dict[str, Any]]) -> str:
    """Format menu items into consolidated text format.

    Args:
        menu_items: List of parsed menu item dictionaries

    Returns:
        str: Formatted consolidated menu text
    """
    # Group items by category
    categories = defaultdict(list)
    for item in menu_items:
        categories[item["category"]].append(item)

    output_parts = []

    for category in categories.keys():
        if category == "Apps":
            output_parts.append("## Appetizers")
        else:
            output_parts.append(f"## {category}")

        for item in categories[category]:
            # Format item name with description
            if item["description"]:
                name_line = f"### {item['name']} - {item['description']}"
            else:
                name_line = f"### {item['name']}"
            output_parts.append(name_line)

            # Format prices
            if item["prices"]:
                if len(item["prices"]) == 1:
                    price_str = item["prices"][0]
                    if "(" in price_str:
                        price_val = price_str.split(" (")[0]
                        output_parts.append(f"Prices: {price_val}")
                    else:
                        output_parts.append(f"Prices: {price_str}")
                else:
                    price_parts = []
                    for price in item["prices"]:
                        if "(" in price:
                            price_val, size_info = price.split(" (", 1)
                            size_info = size_info.rstrip(")")
                            price_parts.append(f"{price_val} ({size_info})")
                        else:
                            price_parts.append(price)
                    output_parts.append(f"Prices: {', '.join(price_parts)}")

            # Format included items
            if item["included"]:
                included_str = ", ".join(item["included"])
                output_parts.append(f"Included in the price: {included_str}")

            output_parts.append("")  # Empty line between items

    return "\n".join(output_parts)
