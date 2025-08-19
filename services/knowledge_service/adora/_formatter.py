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
from typing import Any, Dict, List, Tuple

from ._utils import get_category_name, get_modifier_group_name, get_size_description


def _get_modifier_pricing_text(mod: Dict[str, Any], sizes: List[Dict[str, Any]]) -> str:
    """Get pricing text for a modifier.

    Args:
        mod: Modifier dictionary containing price information
        sizes: List of size dictionaries for size name lookups

    Returns:
        str: Formatted pricing text (e.g., " (+$1.50)" or " (+$0.50 Small, +$1.00 Medium)")
    """
    prices = mod.get("price", [])
    if not prices:
        return ""

    # Check if all prices are the same
    price_values = [p.get("price", 0.0) for p in prices]
    unique_prices = list(set(price_values))

    if len(unique_prices) == 1:
        # All prices are the same
        price_val = unique_prices[0]
        if price_val == 0.0:
            return ""  # Don't show anything when price is not available
        return f" (+${price_val:.1f})"
    else:
        # Different prices for different sizes
        price_parts = []
        for price_info in prices:
            price_val = price_info.get("price", 0.0)
            size_id = price_info.get("size_id")
            size_desc = (
                get_size_description(sizes, size_id) if size_id else "Unknown size"
            )

            # Extract just the size name (before any comma)
            size_name = size_desc.split(",")[0].strip()

            if price_val != 0.0:
                price_parts.append(f"+${price_val:.1f} {size_name}")
            # Skip zero prices entirely - don't show anything

        if price_parts:
            return f" ({', '.join(price_parts)})"

    return ""


def generate_item_text(
    item: Dict[str, Any],
    menu_data: Dict[str, Any],
    with_ids: bool = False,
) -> Tuple[str, str, str]:
    """Generate text representation of a menu item.

    Args:
        item: The menu item dictionary
        menu_data: The complete menu data dictionary
        with_ids: Whether to include IDs in the output

    Returns:
        Tuple[str, str, str]: A tuple containing (item_text, item_name, category_name)
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
                    # Don't show pricing for included modifiers
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
                    pricing_text = _get_modifier_pricing_text(mod, sizes)
                    if with_ids:
                        lines.append(
                            f"- {modifier_name} (modifier_id: {mod.get('modifier_id')}){pricing_text}"
                        )
                    else:
                        lines.append(f"- {modifier_name}{pricing_text}")

            lines.append("")

    item_text = "\n".join(lines)
    return item_text, item_name, category_name


def _format_customizations(modifier_groups: List[Dict[str, Any]]) -> str:
    """Format modifier groups into customizations line.

    Args:
        modifier_groups: List of modifier group dictionaries with pricing info

    Returns:
        str: Formatted customizations string
    """
    if not modifier_groups:
        return ""

    customization_parts = []

    for group in modifier_groups:
        group_name = group["name"].lower()
        optional_modifiers = group.get("optional", [])

        if optional_modifiers:
            # Format: group_name (Optional, Select any number): item1 (+$0.0), item2 (+$0.0)
            modifier_list = []
            for modifier in optional_modifiers:
                # Extract pricing info if available
                pricing_text = modifier.get("pricing", "")
                if pricing_text:
                    modifier_list.append(f"{modifier['name']}{pricing_text}")
                else:
                    modifier_list.append(
                        f"{modifier['name']}"
                    )  # Just the name, no pricing info

            customization_part = f"{group_name} (Optional, Select any number): {', '.join(modifier_list)}"
            customization_parts.append(customization_part)

    if customization_parts:
        return f"  Customizations: {'; '.join(customization_parts)}"

    return ""


def format_consolidated_menu(
    menu_items: List[Dict[str, Any]], include_customizations: bool = True
) -> str:
    """Format menu items into consolidated text format using original structure.

    Args:
        menu_items: List of parsed menu item dictionaries
        include_customizations: Whether to include customization information in the output

    Returns:
        str: Formatted consolidated menu text in original format
    """
    # Group items by category
    categories = defaultdict(list)
    for item in menu_items:
        categories[item["category"]].append(item)

    output_parts = []

    for category in categories.keys():
        if category == "Apps":
            output_parts.append("## Appetizers and Wings")
        else:
            output_parts.append(f"## {category}")

        for item in categories[category]:
            # Format using original structure: ### Item Name - Description
            item_name = item["name"]
            description = item.get("description", "")

            if description:
                header_line = f"### {item_name} - {description}"
            else:
                header_line = f"### {item_name}"
            output_parts.append(header_line)

            # Format prices using original structure: Prices: $X.XX (size), $Y.YY (size)
            prices = item.get("prices", [])
            if prices:
                if len(prices) == 1:
                    # Single price
                    price_str = prices[0]
                    if " (" in price_str:
                        # Extract just the price part before size info
                        price_part = price_str.split(" (")[0]
                        output_parts.append(f"Prices: {price_part}")
                    else:
                        output_parts.append(f"Prices: {price_str}")
                else:
                    # Multiple prices
                    price_strs = []
                    for price in prices:
                        # Prices already include size info like "$8.99 (6pc)"
                        price_strs.append(price)
                    output_parts.append(f"Prices: {', '.join(price_strs)}")

            # Add "Included in the price" section using original structure
            included_items = []
            modifier_groups = item.get("modifier_groups", [])
            for group in modifier_groups:
                included_modifiers = group.get("included", [])
                for modifier in included_modifiers:
                    if isinstance(modifier, dict):
                        included_items.append(modifier["name"])
                    else:
                        included_items.append(modifier)

            if included_items:
                output_parts.append(
                    f"Included in the price: {', '.join(included_items)}"
                )

            # Add customizations section (NEW) - only if enabled
            if include_customizations:
                customizations_line = _format_customizations_legacy(modifier_groups)
                if customizations_line:
                    output_parts.append(customizations_line)

            output_parts.append("")  # Empty line between items

    return "\n".join(output_parts)


def _format_customizations_legacy(modifier_groups: List[Dict[str, Any]]) -> str:
    """Format customizations for legacy format.

    Args:
        modifier_groups: List of modifier group dictionaries

    Returns:
        str: Formatted customizations line
    """
    if not modifier_groups:
        return ""

    customization_parts = []
    for group in modifier_groups:
        group_name = group["name"].lower()
        optional_modifiers = group.get("optional", [])

        if optional_modifiers:
            modifier_list = []
            for modifier in optional_modifiers:
                if isinstance(modifier, dict):
                    pricing_text = modifier.get("pricing", "")
                    if pricing_text:
                        modifier_list.append(f"{modifier['name']}{pricing_text}")
                    else:
                        modifier_list.append(
                            f"{modifier['name']}"
                        )  # Just the name, no pricing info
                else:
                    modifier_list.append(
                        f"{modifier}"
                    )  # Just the name, no pricing info

            if modifier_list:
                customization_part = f"{group_name} (Optional, Select any number): {', '.join(modifier_list)}"
                customization_parts.append(customization_part)

    if customization_parts:
        return f"Customizations: {'; '.join(customization_parts)}"

    return ""
