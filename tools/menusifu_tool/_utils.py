"""
Utility functions for MenuSifu tool operations
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from .classes import (
    Category,
    ComboSection,
    DetailPrice,
    LocalizedName,
    MenuGroup,
    MenuResponse,
    Price,
    Property,
    SaleItem,
    Size,
)


def _localized_to_text(
    value: Union[str, LocalizedName, Size, Dict[str, Any], None],
    locale: str,
) -> str:
    """Return localized string for provided value with sensible fallbacks.

    Locale priority: exact locale -> 'en' -> first available -> "".
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (LocalizedName, Size)):
        data = value.dict(by_alias=True, exclude_none=True)
    elif isinstance(value, dict):
        data = {k: v for k, v in value.items() if v}
    else:
        # Unknown type – best effort string
        return str(value)

    if not data:
        return ""
    if locale in data and data[locale]:
        return data[locale]
    if "en" in data and data["en"]:
        return data["en"]
    # Fallback to any available value
    return next(iter(data.values()))


def _format_prices(item) -> List[str]:
    """Return human-friendly price list for a sale item.

    Supports either flat price or detail prices with sizes.
    Excludes zero prices and null prices without base prices to avoid showing free add-ons.
    """
    prices: List[str] = []

    # Handle both object and dict access patterns
    item_price = getattr(item, "price", None) if hasattr(item, "price") else None
    item_base_price = (
        getattr(item, "base_price", None)
        if hasattr(item, "base_price")
        else getattr(item, "basePrice", None) if hasattr(item, "basePrice") else None
    )
    item_detail_price = (
        getattr(item, "detail_price", None) if hasattr(item, "detail_price") else None
    )

    # Try base_price first if price is None, but skip zero prices
    price_to_use = item_price if item_price is not None else item_base_price

    if price_to_use is not None:
        try:
            price_value = float(price_to_use)
            # Only show non-zero prices
            if price_value > 0:
                prices.append(f"${price_value:.2f}")
        except Exception:
            # If it's not a number, show it anyway
            if str(price_to_use) != "0":
                prices.append(str(price_to_use))

    if item_detail_price and isinstance(item_detail_price, DetailPrice):
        for p in item_detail_price.prices:
            if isinstance(p, Price):
                try:
                    price_value = float(p.price)
                    # Only show non-zero prices
                    if price_value > 0:
                        size_name = _localized_to_text(p.size, "en") if p.size else ""
                        price_text = f"${price_value:.2f}"
                        if size_name:
                            prices.append(f"{price_text} ({size_name})")
                        else:
                            prices.append(price_text)
                except Exception:
                    # If it's not a number, show it anyway (unless it's "0")
                    if str(p.price) != "0":
                        size_name = _localized_to_text(p.size, "en") if p.size else ""
                        price_text = str(p.price)
                        if size_name:
                            prices.append(f"{price_text} ({size_name})")
                        else:
                            prices.append(price_text)

    # Ensure uniqueness while preserving order
    seen = set()
    unique_prices: List[str] = []
    for pr in prices:
        if pr not in seen:
            unique_prices.append(pr)
            seen.add(pr)
    return unique_prices


def _extract_properties(item) -> List[str]:
    """Extract boolean properties as tags (e.g., Spicy, Recommended, New).

    Supports various property types including:
    - SPICY: Shows spiciness level or indicator
    - RECOMMENDED: Shows recommended items
    - NEW: Shows new items
    """
    tags: List[str] = []

    # Handle both object and dict access patterns
    item_properties = (
        getattr(item, "properties", None) if hasattr(item, "properties") else None
    )

    if item_properties:
        for prop in item_properties or []:
            if isinstance(prop, Property):
                # Check for different property types and values
                if prop.value is True or prop.value is None:
                    name = prop.display_name or prop.name
                    if name:
                        tags.append(str(name))
                elif prop.name in ["SPICY", "RECOMMENDED", "NEW"] and prop.value:
                    # Handle special property types with custom display
                    display_name = prop.display_name or prop.name
                    if prop.name == "SPICY" and display_name == "Spicy":
                        tags.append("Spicy")
                    elif prop.name == "RECOMMENDED" and display_name == "Recommended":
                        tags.append("Recommended")
                    elif prop.name == "NEW":
                        tags.append("New")
                    else:
                        tags.append(str(display_name))
            elif isinstance(prop, dict):
                prop_name = prop.get("name", "")
                prop_value = prop.get("value")
                display_name = prop.get("displayName") or prop_name

                if prop_value is True or prop_value is None:
                    if display_name:
                        tags.append(str(display_name))
                elif prop_name in ["SPICY", "RECOMMENDED", "NEW"] and prop_value:
                    # Handle special property types with custom display
                    if prop_name == "SPICY" and display_name == "Spicy":
                        tags.append("Spicy")
                    elif prop_name == "RECOMMENDED" and display_name == "Recommended":
                        tags.append("Recommended")
                    elif prop_name == "NEW":
                        tags.append("New")
                    else:
                        tags.append(str(display_name))
    return tags


def _format_price(price) -> str:
    """Format price for options/sub-options.

    Returns empty string for None or zero/"0", "+$<n>.nn" for numeric >0,
    or "+<raw>" for non-numeric non-"0" values.
    """
    if price is None:
        return ""

    try:
        price_value = float(price)
        # Only show non-zero prices
        if price_value > 0:
            return f"+${price_value:.2f}"
        else:
            return ""
    except Exception:
        # If it's not a number, show it anyway (unless it's "0")
        if str(price) != "0":
            return f"+{price}"
        else:
            return ""


def _render_subparts(subs, locale: str) -> List[str]:
    """Render sub-options as name (+price?) strings."""
    subparts: List[str] = []

    for sub in subs:
        # Handle both object and dict access patterns
        if hasattr(sub, "name") and hasattr(sub, "price"):
            # Object access
            sub_name = _localized_to_text(sub.name, locale)
            price_text = _format_price(sub.price)
        else:
            # Dict access
            sub_name = _localized_to_text(sub.get("name", {}), locale)
            price_text = _format_price(sub.get("price"))

        subparts.append(f"{sub_name}{(' ' + price_text) if price_text else ''}")

    return subparts


def _append_option_line(
    option_lines: List[str], name: str, price_text: str, subparts: List[str]
) -> None:
    """Append option line in appropriate format based on price and subparts."""
    if subparts:
        # Has sub-options: "Name: sub1, sub2"
        option_lines.append(f"{name}: {', '.join(subparts)}")
    elif price_text:
        # Has price: "Name +price"
        option_lines.append(f"{name} {price_text}")
    else:
        # Just name: "Name"
        option_lines.append(name)


def _extract_bilingual_options(item) -> List[str]:
    """Extract options in bilingual format (English / Chinese)."""
    option_lines: List[str] = []

    # Handle both object and dict access patterns
    item_options = (
        item.get("options", [])
        if isinstance(item, dict)
        else getattr(item, "options", [])
    )

    for opt in item_options:
        if isinstance(opt, dict):
            opt_name_en = opt.get("name", {}).get("en", "")
            opt_name_zh = opt.get("name", {}).get("zh-cn", "")

            if opt_name_en:
                # Create bilingual name
                if opt_name_zh:
                    opt_name = f"{opt_name_en} / {opt_name_zh}"
                else:
                    opt_name = opt_name_en

                # Format price using existing helper
                price_text = _format_price(opt.get("price"))

                # Append using existing helper
                _append_option_line(option_lines, opt_name, price_text, [])

    return option_lines


def _check_item_availability(item) -> Dict[str, Any]:
    """Check item availability status based on soldOut/outOfStock flags.

    Returns availability info with status and reason:
    - 'available': Item can be ordered
    - 'sold_out': Item is sold out, cannot add to cart
    - 'out_of_stock': Item is out of stock, cannot add to cart
    """
    # Handle both object and dict access patterns
    sold_out = (
        getattr(item, "sold_out", None)
        if hasattr(item, "sold_out")
        else item.get("soldOut", False) if isinstance(item, dict) else False
    )
    out_of_stock = (
        getattr(item, "out_of_stock", None)
        if hasattr(item, "out_of_stock")
        else item.get("outOfStock", False) if isinstance(item, dict) else False
    )

    if sold_out:
        return {"status": "sold_out", "reason": "Item is sold out", "can_order": False}
    elif out_of_stock:
        return {
            "status": "out_of_stock",
            "reason": "Item is out of stock",
            "can_order": False,
        }
    else:
        return {"status": "available", "reason": "Item is available", "can_order": True}


def _validate_combo_selection_rules(combo_section) -> Dict[str, Any]:
    """Validate combo section selection rules.

    Checks:
    - itemSelectionRule: 1=equals, 2=min, 3=max, 4=range
    - allowRepeatedItems: whether items can be selected multiple times
    - maxNumOfSelectionAllowed: maximum selections allowed
    - minNumOfSelectionAllowed: minimum selections required
    - priceRule: 1=Adjustable, 2=Fixed, 3=Fixed Until Max
    """
    # Handle both object and dict access patterns
    if isinstance(combo_section, dict):
        selection_rule = combo_section.get("itemSelectionRule", 1)
        allow_repeated = combo_section.get("allowRepeatedItems", False)
        max_selections = combo_section.get("maxNumOfSelectionAllowed", 1)
        min_selections = combo_section.get("minNumOfSelectionAllowed", 1)
        price_rule = combo_section.get("priceRule", 1)
        section_items = combo_section.get("comboSectionSaleItems", [])
    else:
        selection_rule = getattr(combo_section, "item_selection_rule", 1)
        allow_repeated = getattr(combo_section, "allow_repeated_items", False)
        max_selections = getattr(combo_section, "max_num_of_selection_allowed", 1)
        min_selections = getattr(combo_section, "min_num_of_selection_allowed", 1)
        price_rule = getattr(combo_section, "price_rule", 1)
        section_items = getattr(combo_section, "combo_section_sale_items", [])

    # Validate selection rules
    validation_result = {
        "is_valid": True,
        "errors": [],
        "selection_info": {
            "rule_type": _get_selection_rule_name(selection_rule),
            "min_required": min_selections,
            "max_allowed": max_selections,
            "allow_repeated": allow_repeated,
            "price_rule": _get_price_rule_name(price_rule),
        },
    }

    # Check for pre-selected items requirement
    pre_selected_count = sum(
        1
        for item in section_items
        if (
            item.get("preSelected", False)
            if isinstance(item, dict)
            else getattr(item, "pre_selected", False)
        )
    )

    if pre_selected_count > 0:
        validation_result["selection_info"]["pre_selected_count"] = pre_selected_count
        validation_result["selection_info"][
            "note"
        ] = "Has pre-selected items (required in online orders)"

    return validation_result


def _get_selection_rule_name(rule_code: int) -> str:
    """Get human-readable name for selection rule."""
    rule_names = {
        1: "Equals",  # 等于 - EQUALS_TO
        2: "Minimum",  # 最少 - MIN_NUM_LIMIT
        3: "Maximum",  # 最多 - MAX_NUM_LIMIT
        4: "Range",  # 范围 - RANGE
        5: "Range For Fixed Until Max",  # 范围&固定计价 - RANGE_FOR_FIXED_UNTIL_MAX
    }
    return rule_names.get(rule_code, f"Unknown({rule_code})")


def _get_price_rule_name(rule_code: int) -> str:
    """Get human-readable name for price rule."""
    price_rules = {
        1: "Adjustable",  # 子项计价
        2: "Fixed Until Max",  # 超额计价
        3: "Fixed combo price",  # 子项不计价
    }
    return price_rules.get(rule_code, f"Unknown({rule_code})")


def _check_combo_availability(item) -> Dict[str, Any]:
    """Check combo item availability including section validation.

    Returns comprehensive availability status for combo items:
    - Checks main item availability
    - Validates each combo section
    - Identifies unavailable combinations
    """
    availability = _check_item_availability(item)

    # If main item is unavailable, return early
    if not availability["can_order"]:
        return availability

    # Check combo sections if it's a combo item
    item_type = (
        getattr(item, "item_type", None)
        if hasattr(item, "item_type")
        else item.get("itemType", "") if isinstance(item, dict) else ""
    )

    if item_type == "COMBO_SALE_ITEM":
        combo_sections = (
            getattr(item, "combo_sections", [])
            if hasattr(item, "combo_sections")
            else item.get("comboSections", []) if isinstance(item, dict) else []
        )

        section_issues = []
        for i, section in enumerate(combo_sections):
            section_validation = _validate_combo_selection_rules(section)

            # Check if any items in section are unavailable
            # This would need access to the full item data to check availability
            # For now, we'll assume section items follow the same availability rules

            if not section_validation["is_valid"]:
                section_issues.append(
                    f"Section {i+1}: {', '.join(section_validation['errors'])}"
                )

        if section_issues:
            availability.update(
                {
                    "status": "unavailable",
                    "reason": f"Combo configuration issues: {'; '.join(section_issues)}",
                    "can_order": False,
                    "section_issues": section_issues,
                }
            )

    return availability


def generate_combo_details(item) -> Dict[str, Any]:
    """Generate detailed combo information including rules and constraints."""
    combo_details = {
        "is_combo": False,
        "sections": [],
        "availability": _check_combo_availability(item),
    }

    # Check if it's a combo item
    item_type = (
        getattr(item, "item_type", None)
        if hasattr(item, "item_type")
        else item.get("itemType", "") if isinstance(item, dict) else ""
    )

    if item_type == "COMBO_SALE_ITEM":
        combo_details["is_combo"] = True

        combo_sections = (
            getattr(item, "combo_sections", [])
            if hasattr(item, "combo_sections")
            else item.get("comboSections", []) if isinstance(item, dict) else []
        )

        for section in combo_sections:
            section_info = _validate_combo_selection_rules(section)
            combo_details["sections"].append(section_info)

    return combo_details


def clean_item_name(name: str) -> str:
    """
    Clean item names by removing ^ or ~ prefixes and other unwanted characters.

    Args:
        name: Raw item name

    Returns:
        str: Cleaned item name
    """
    if not name:
        return ""

    # Remove ^ or ~ prefixes
    cleaned = name.lstrip("^~")

    # Remove extra whitespace
    cleaned = cleaned.strip()

    return cleaned


def is_internal_category(category_name_en: str, category_name_zh: str) -> bool:
    """
    Check if a category is for internal system use and should not appear in customer menus.

    Args:
        category_name_en: English category name
        category_name_zh: Chinese category name

    Returns:
        bool: True if this is an internal category
    """
    if not category_name_en and not category_name_zh:
        return True

    # Check for internal system markers
    internal_markers = [
        "don't delete",
        "不能删",
        "do not delete",
        "system",
        "internal",
        "combo items",
        "组合商品",
        "temp",
        "temporary",
        "test",
        "测试",
    ]

    combined_text = f"{category_name_en.lower()} {category_name_zh.lower()}"

    return any(marker in combined_text for marker in internal_markers)


def get_section_description(section_name_en: str, section_name_zh: str) -> str:
    """
    Get helpful description for common combo sections to explain their purpose.

    Args:
        section_name_en: English section name
        section_name_zh: Chinese section name

    Returns:
        str: Helpful description or empty string
    """
    section_descriptions = {
        "lunch with": "Rice/starch selection",
        "rice modify": "Ingredients to exclude",
        "rice": "Rice/starch base",
        "protein": "Main protein",
        "vegetable": "Vegetable sides",
        "sauce": "Sauce/seasoning",
        "side": "Additional sides",
        "soup": "Soup selection",
        "drink": "Beverage",
        "appetizer": "Appetizer",
        "dessert": "Dessert",
    }

    # Check English name first
    section_key = section_name_en.lower().strip()
    if section_key in section_descriptions:
        return section_descriptions[section_key]

    # Check for partial matches
    for key, description in section_descriptions.items():
        if key in section_key or section_key in key:
            return description

    return ""


def get_selection_rule_description(
    rule: int, min_sel: int, max_sel: int, allow_repeated: bool
) -> str:
    """
    Get human-readable selection rule description based on MenuSifu documentation.

    Args:
        rule: itemSelectionRule (1-5)
        min_sel: minNumOfSelectionAllowed
        max_sel: maxNumOfSelectionAllowed
        allow_repeated: allowRepeatedItems

    Returns:
        str: Human-readable rule description
    """
    repeat_text = (
        " (items can be repeated)" if allow_repeated else " (no repeats allowed)"
    )

    if rule == 1:  # EQUALS_TO - 等于
        return f"Must choose exactly {min_sel} item{'s' if min_sel != 1 else ''}{repeat_text}"
    elif rule == 2:  # MIN_NUM_LIMIT - 最少
        return (
            f"Choose at least {min_sel} item{'s' if min_sel != 1 else ''}{repeat_text}"
        )
    elif rule == 3:  # MAX_NUM_LIMIT - 最多
        return f"Choose up to {max_sel} item{'s' if max_sel != 1 else ''}{repeat_text}"
    elif rule == 4:  # RANGE - 范围
        return f"Choose {min_sel}-{max_sel} items{repeat_text}"
    elif rule == 5:  # RANGE_FOR_FIXED_UNTIL_MAX - 范围&固定计价
        return f"Choose {min_sel}-{max_sel} items (special pricing beyond {max_sel}){repeat_text}"
    else:
        return f"Selection required{repeat_text}"


def get_price_rule_description(price_rule: int) -> str:
    """
    Get human-readable pricing rule description based on MenuSifu documentation.

    Args:
        price_rule: priceRule (1-3)

    Returns:
        str: Human-readable pricing description
    """
    if price_rule == 1:  # ADJUSTABLE_PRICE - 子菜计价
        return "Individual item prices apply"
    elif price_rule == 2:  # FIXED_UNTIL_MAX - 超额计价
        return "Fixed combo price until maximum, then individual prices for extras"
    elif price_rule == 3:  # FIXED_PRICE - 子菜不计价
        return "Fixed combo price (no extra charges)"
    else:
        return "Pricing rules apply"


def check_combo_section_availability(section, item_lookup: dict) -> dict:
    """
    Check if a combo section can be completed based on MenuSifu business rules.

    Args:
        section: Combo section object
        item_lookup: Dictionary mapping item IDs to item details

    Returns:
        dict: Availability status and details
    """
    if not section.combo_section_sale_items:
        return {
            "available": False,
            "reason": "No items available in this section",
            "available_count": 0,
            "required_count": section.min_num_of_selection_allowed or 0,
        }

    available_items = 0
    out_of_stock_items = 0

    for combo_item in section.combo_section_sale_items:
        item_details = item_lookup.get(combo_item.sale_item_id, {})
        if item_details.get("out_of_stock", False):
            # Only count truly out-of-stock items as unavailable
            out_of_stock_items += 1
        else:
            # Hidden items are still available in combo context
            # (they're hidden from regular menu but valid combo choices)
            available_items += 1

    min_required = section.min_num_of_selection_allowed or 0

    # Check if section can be completed
    can_complete = available_items >= min_required

    return {
        "available": can_complete,
        "reason": (
            f"Only {available_items} items available, need at least {min_required}"
            if not can_complete
            else "Section available"
        ),
        "available_count": available_items,
        "required_count": min_required,
        "out_of_stock_count": out_of_stock_items,
        "total_items": len(section.combo_section_sale_items),
    }


def create_item_lookup(menu: MenuResponse) -> dict:
    """
    Create a lookup dictionary mapping sale item IDs to their details.
    Based on the official API spec for MenuSifu responses.

    This includes ALL items from ALL categories, including internal ones,
    so combo sections can find their referenced items.

    Args:
        menu: MenuResponse object containing menu data

    Returns:
        dict: Mapping of item_id -> item details with cleaned names
    """
    item_lookup = {}

    for group in menu.groups:
        for category in group.categories:
            # Include items from ALL categories (including internal ones) for combo lookup
            category_name = category.name.en if category.name.en else ""
            for item in category.sale_items:
                # Clean the names according to the spec
                clean_name_en = clean_item_name(item.name.en if item.name.en else "")
                clean_name_zh = clean_item_name(
                    item.name.zh_cn if item.name.zh_cn else ""
                )

                item_lookup[item.id] = {
                    "name_en": clean_name_en,
                    "name_zh": clean_name_zh,
                    "item_type": item.item_type,
                    "category": category_name,
                    "price": item.price,
                    "base_price": getattr(item, "base_price", None),
                    "out_of_stock": getattr(item, "out_of_stock", False),
                    "hidden_item": getattr(item, "hidden_item", False),
                    "from_internal_category": is_internal_category(
                        clean_item_name(category.name.en if category.name.en else ""),
                        clean_item_name(
                            category.name.zh_cn if category.name.zh_cn else ""
                        ),
                    ),
                }

    return item_lookup


def generate_bilingual_menu_content(menu: MenuResponse) -> str:
    """
    Generate bilingual menu content based on official MenuSifu API specs.

    Features implemented according to API documentation:
    - Cleans item names by removing ^ or ~ prefixes
    - Handles hidden items and categories (skips them)
    - Shows out of stock status
    - Detailed combo information with proper selection rules
    - Bilingual support for all text elements
    - Group hours and descriptions
    - Required category marking
    - Combo type and pricing rule information

    Args:
        menu: MenuResponse object containing menu data

    Returns:
        str: Bilingual menu content with comprehensive combo details
    """
    lines = []

    # Create item lookup for combo resolution
    item_lookup = create_item_lookup(menu)

    # Menu title - cleaned according to API specs
    menu_name_en = clean_item_name(menu.name.en if menu.name.en else "Menu")
    menu_name_zh = clean_item_name(menu.name.zh_cn if menu.name.zh_cn else "")

    if menu_name_zh:
        lines.append(f"{menu_name_en} / {menu_name_zh}")
    else:
        lines.append(menu_name_en)
    lines.append("=" * len(lines[-1]))
    lines.append("")

    # Process groups and categories according to API specs
    for group in menu.groups:
        # Group name - cleaned
        group_name_en = clean_item_name(group.name.en if group.name.en else "")
        group_name_zh = clean_item_name(group.name.zh_cn if group.name.zh_cn else "")

        if group_name_en:
            if group_name_zh:
                group_title = f"{group_name_en} / {group_name_zh}"
            else:
                group_title = group_name_en

            lines.append(f"# {group_title}")

            # Compact group info on single line
            group_info = []
            if hasattr(group, "description") and group.description:
                group_info.append(group.description)

            # Simplified hours
            if hasattr(group, "hours") and group.hours:
                hour_texts = []
                for hour in group.hours:
                    if hasattr(hour, "name") and hour.name:
                        from_time = getattr(
                            hour, "from_time", getattr(hour, "from", "Unknown")
                        )
                        to_time = getattr(
                            hour, "to_time", getattr(hour, "to", "Unknown")
                        )
                        if from_time != "Unknown" and to_time != "Unknown":
                            hour_texts.append(f"{from_time}-{to_time}")
                if hour_texts:
                    group_info.append(f"Hours: {' | '.join(hour_texts)}")

            if group_info:
                lines.append(f"*{' | '.join(group_info)}*")

            lines.append("")

        # Process categories
        for category in group.categories:
            # Skip hidden categories as per API spec
            if getattr(category, "hidden_category", False):
                continue

            # Category name - cleaned
            cat_name_en = clean_item_name(category.name.en if category.name.en else "")
            cat_name_zh = clean_item_name(
                category.name.zh_cn if category.name.zh_cn else ""
            )

            # Skip internal system categories (like "Combo Items DON'T DELETE")
            if is_internal_category(cat_name_en, cat_name_zh):
                continue

            # First, collect all valid items for this category
            category_lines = []

            # Process items to see if any are valid
            for item in category.sale_items:

                # Get prices (filtered for zero prices)
                prices = _format_prices(item)

                # Skip items with no valid prices (zero prices filtered out)
                # Exception: Don't skip combo items that might have zero prices
                if not prices and item.item_type != "COMBO_SALE_ITEM":
                    continue

                # Item names - cleaned according to API specs
                item_name_en = clean_item_name(item.name.en if item.name.en else "")
                item_name_zh = clean_item_name(
                    item.name.zh_cn if item.name.zh_cn else ""
                )

                # Skip hidden items as per API spec
                if getattr(item, "hidden_item", False):
                    continue

                if item_name_en:
                    # This is a valid item, add it to the category
                    if item_name_zh:
                        item_title = f"{item_name_en} / {item_name_zh}"
                    else:
                        item_title = item_name_en

                    # Compact format: combine price, availability, and properties on one line
                    price_text = ", ".join(prices)
                    item_line = f"• {item_title} - {price_text}"

                    # Add properties inline if available
                    properties = _extract_properties(item)
                    if properties:
                        item_line += f" [{', '.join(properties)}]"

                    # Add availability status inline
                    availability = _check_item_availability(item)
                    if not availability["can_order"]:
                        item_line += f" [UNAVAILABLE: {availability['status'].upper()}]"
                    elif getattr(item, "out_of_stock", False):
                        item_line += " [OUT OF STOCK]"

                    category_lines.append(item_line)

                    # Compact combo details format
                    if item.item_type == "COMBO_SALE_ITEM" and item.combo_sections:
                        # Compact combo header with type and price
                        combo_type = getattr(item, "combo_type", None)
                        combo_info = "COMBO"
                        if combo_type == 1:
                            combo_info += " (Fixed)"
                        elif combo_type == 2:
                            combo_info += " (Flexible)"

                        base_price = getattr(item, "base_price", None)
                        if base_price:
                            try:
                                numeric_base_price = float(base_price)
                                numeric_item_price = (
                                    float(item.price) if item.price is not None else 0
                                )
                                if numeric_base_price != numeric_item_price:
                                    combo_info += f" - Base: ${numeric_base_price:.2f}"
                            except (ValueError, TypeError):
                                # Skip formatting for non-numeric base_price
                                pass

                        category_lines.append(f"  {combo_info}:")

                        # Check overall combo availability and process sections with business rules
                        combo_unavailable_sections = []
                        combo_has_issues = False

                        # Process each combo section with MenuSifu business rules
                        for i, section in enumerate(item.combo_sections):
                            # Check section availability first
                            section_availability = check_combo_section_availability(
                                section, item_lookup
                            )

                            section_items = []
                            section_pre_selected = []
                            section_unavailable_items = []

                            if section.combo_section_sale_items:
                                for combo_item in section.combo_section_sale_items:
                                    item_details = item_lookup.get(
                                        combo_item.sale_item_id, {}
                                    )

                                    # Get item names - ensure we map ALL combo items to actual dishes
                                    if item_details:
                                        # Get the cleaned names (^ prefix already removed by clean_item_name)
                                        item_name_en = item_details.get("name_en", "")
                                        item_name_zh = item_details.get("name_zh", "")

                                        # Create proper bilingual dish name
                                        if item_name_zh and item_name_en:
                                            dish_name = (
                                                f"{item_name_en} / {item_name_zh}"
                                            )
                                        elif item_name_en:
                                            dish_name = item_name_en
                                        else:
                                            dish_name = f"Unknown Item {combo_item.sale_item_id}"
                                    else:
                                        # Item not found in lookup - shouldn't happen but handle gracefully
                                        dish_name = f"Item ID {combo_item.sale_item_id} [NOT IN LOOKUP]"

                                    # Check availability and include ALL combo items regardless of hidden status
                                    if item_details and item_details.get(
                                        "out_of_stock", False
                                    ):
                                        dish_name += " (SOLD OUT)"
                                        section_unavailable_items.append(dish_name)
                                        combo_has_issues = True
                                    else:
                                        # Include ALL combo items - hidden items are valid combo choices
                                        # Add pricing info using safe formatting
                                        if item_details:
                                            formatted_price = _format_price(
                                                item_details.get("price")
                                            )
                                            if formatted_price:
                                                dish_name += f" ({formatted_price})"

                                        if combo_item.pre_selected:
                                            section_pre_selected.append(dish_name)
                                        else:
                                            section_items.append(dish_name)

                            # Create section title with bilingual support
                            section_name_en = clean_item_name(
                                section.name.en if section.name.en else ""
                            )
                            section_name_zh = clean_item_name(
                                section.name.zh_cn if section.name.zh_cn else ""
                            )

                            if section_name_en and section_name_zh:
                                section_title = f"{section_name_en} / {section_name_zh}"
                            elif section_name_en:
                                section_title = section_name_en
                            else:
                                section_title = f"Section {i + 1}"

                            # Get detailed rule descriptions from MenuSifu documentation
                            rule = section.item_selection_rule
                            min_sel = section.min_num_of_selection_allowed or 0
                            max_sel = section.max_num_of_selection_allowed or 0
                            allow_repeated = getattr(
                                section, "allow_repeated_items", False
                            )

                            selection_rule = get_selection_rule_description(
                                rule, min_sel, max_sel, allow_repeated
                            )
                            pricing_rule = get_price_rule_description(
                                section.price_rule
                            )

                            # Compact section header with all info on one line
                            section_description = get_section_description(
                                section_name_en, section_name_zh
                            )
                            description_text = (
                                f" ({section_description})"
                                if section_description
                                else ""
                            )

                            if not section_availability["available"]:
                                category_lines.append(
                                    f"    • {section_title}{description_text} - UNAVAILABLE: {section_availability['reason']}"
                                )
                                combo_unavailable_sections.append(section_title)
                                combo_has_issues = True
                            else:
                                category_lines.append(
                                    f"    • {section_title}{description_text}:"
                                )
                                # Combine rules and pricing on one line
                                category_lines.append(
                                    f"      {selection_rule} | {pricing_rule}"
                                )

                            # Compact display of items
                            if section_pre_selected:
                                category_lines.append(
                                    f"      Required: {' | '.join(section_pre_selected)}"
                                )

                            # Display choice items more compactly
                            if section_items:
                                available_count = len(section_items)
                                category_lines.append(
                                    f"      Choices ({available_count}): {' | '.join(section_items)}"
                                )

                            # Display unavailable items compactly
                            if section_unavailable_items:
                                category_lines.append(
                                    f"      Unavailable: {' | '.join(section_unavailable_items)}"
                                )

                            # Debug: If still no items are shown, provide detailed info
                            if (
                                not section_items
                                and not section_pre_selected
                                and not section_unavailable_items
                            ):
                                if section.combo_section_sale_items:
                                    # This should rarely happen now - let's debug what's going wrong
                                    missing_items = []
                                    for combo_item in section.combo_section_sale_items:
                                        if combo_item.sale_item_id not in item_lookup:
                                            missing_items.append(
                                                str(combo_item.sale_item_id)
                                            )

                                    if missing_items:
                                        category_lines.append(
                                            f"      ERROR: Items not found in lookup: {', '.join(missing_items)}"
                                        )
                                    else:
                                        category_lines.append(
                                            "      ERROR: Items exist but filtered out unexpectedly"
                                        )
                                else:
                                    category_lines.append(
                                        "      Items: No items configured for this section"
                                    )

                        # Compact combo status
                        if combo_unavailable_sections:
                            category_lines.append(
                                f"  ⚠️ Issues: {', '.join(combo_unavailable_sections)}"
                            )
                        elif combo_has_issues:
                            category_lines.append("  ℹ️ Some items sold out")

                    # Add options compactly
                    options = _extract_bilingual_options(item)
                    if options:
                        cleaned_options = [
                            clean_item_name(opt)
                            for opt in options
                            if clean_item_name(opt)
                        ]
                        if cleaned_options:
                            # Show all options without truncation
                            category_lines.append(
                                f"  Options: {' | '.join(cleaned_options)}"
                            )

            # Only add category header and items if there are valid items
            if category_lines and cat_name_en:
                if cat_name_zh:
                    cat_title = f"## {cat_name_en} / {cat_name_zh}"
                else:
                    cat_title = f"## {cat_name_en}"
                lines.append(cat_title)

                # Add category description and required status inline
                category_details = []
                if category.description:
                    category_details.append(category.description)
                if getattr(category, "require_category", False):
                    category_details.append("(Required)")

                if category_details:
                    lines.append(f"*{' | '.join(category_details)}*")

                # Add all the category items
                lines.extend(category_lines)
                lines.append("")  # Space after each category

    return "\n".join(lines).strip()


# MenuSifu API Filtering Functions
# Based on API error conditions: CLOSING, DELETED, ITEM_HIDDEN, SOLD_OUT, OUT_OF_STOCK, OPTION_LIMIT


def is_item_available_by_time(
    item: Union[SaleItem, Dict[str, Any]],
    group_hours: Optional[List[Dict[str, Any]]] = None,
    current_time: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Check if item is available during current time based on group hours.

    Note: Individual items don't have groupHours in MenuSifu - time restrictions
    are at the group level. This function checks if the group containing this
    item is currently open.

    API Error: CLOSING - "Some sale item is not available. the sale item is:..."

    Args:
        item: SaleItem model or item data dict from menu response
        group_hours: Hours from the MenuGroup containing this item
        current_time: Current datetime (defaults to now)

    Returns:
        dict: {"available": bool, "reason": str, "hours": list}
    """
    if current_time is None:
        current_time = datetime.now()

    # If no group hours provided, assume available all day
    if not group_hours:
        return {"available": True, "reason": "No time restrictions", "hours": []}

    # Get day of week (1=Monday, 7=Sunday, MenuSifu uses 1-7)
    current_day = current_time.isoweekday()  # 1=Monday, 7=Sunday
    current_time_str = current_time.strftime("%H:%M")

    # Check each time period
    for period in group_hours:
        from_day = period.get("fromDayOfTheWeek", 1)
        to_day = period.get("toDayOfTheWeek", 7)
        from_time = period.get("from", "00:00")
        to_time = period.get("to", "23:59")

        # Check if current day is within the period
        day_in_range = False
        if from_day <= to_day:
            # Normal range (e.g., Mon-Fri)
            day_in_range = from_day <= current_day <= to_day
        else:
            # Wrap-around range (e.g., Fri-Mon)
            day_in_range = current_day >= from_day or current_day <= to_day

        if day_in_range:
            # Check if current time is within the period
            if from_time <= current_time_str <= to_time:
                return {
                    "available": True,
                    "reason": f"Available during {period.get('name', 'period')}",
                    "hours": group_hours,
                }

    # Not available during current time
    return {
        "available": False,
        "reason": "Not available during current time",
        "hours": group_hours,
    }


def is_item_not_deleted(item: Union[SaleItem, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Check if item is not deleted.

    Note: In the actual MenuSifu menu response, sale items don't have a 'deleted' field.
    The DELETED error occurs when trying to order an item that was removed from the menu
    but is no longer present in the API response. This function always returns True
    for items that exist in the menu response.

    API Error: DELETED - "\"item_name\" item is deleted."

    Args:
        item: SaleItem model or item data dict from menu response

    Returns:
        dict: {"available": bool, "reason": str, "deleted": bool}
    """
    # If the item exists in the menu response, it's not deleted
    # The 'deleted' field doesn't exist on sale items in the actual API response
    return {
        "available": True,
        "reason": "Item exists in menu (not deleted)",
        "deleted": False,
    }


def is_item_not_hidden(item: Union[SaleItem, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Check if item is not hidden (hiddenItem = false).

    API Error: ITEM_HIDDEN - "\"item_name\" item is hidden."

    Args:
        item: SaleItem model or item data dict from menu response

    Returns:
        dict: {"available": bool, "reason": str, "hidden": bool}
    """
    if isinstance(item, SaleItem):
        hidden = item.hidden_item
    else:
        hidden = item.get("hiddenItem", False)

    if hidden:
        return {"available": False, "reason": "Item is hidden", "hidden": True}
    else:
        return {"available": True, "reason": "Item is visible", "hidden": False}


def is_item_in_stock(item: Union[SaleItem, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Check if item is in stock (not sold out or out of stock).

    API Error: SOLD_OUT - "\"item_name\" item is sold out."
    API Error: OUT_OF_STOCK - "\"item_name\" item is deleted." (same message, different type)

    Args:
        item: SaleItem model or item data dict from menu response

    Returns:
        dict: {"available": bool, "reason": str, "out_of_stock": bool, "sold_out": bool}
    """
    if isinstance(item, SaleItem):
        out_of_stock = item.out_of_stock
    else:
        out_of_stock = item.get("outOfStock", False)

    # Note: MenuSifu doesn't seem to have a separate "soldOut" field in the menu response
    # The SOLD_OUT error is determined at order time based on current inventory

    if out_of_stock:
        return {
            "available": False,
            "reason": "Item is out of stock",
            "out_of_stock": True,
            "sold_out": False,
        }
    else:
        return {
            "available": True,
            "reason": "Item is in stock",
            "out_of_stock": False,
            "sold_out": False,
        }


def validate_option_quantities(
    selected_options: List[Dict[str, Any]], item_max_options: int
) -> Dict[str, Any]:
    """
    Validate that option quantities are within allowed limits.

    API Error: OPTION_LIMIT - "There is a limit to the number of options for item \"item_name\"."

    Args:
        selected_options: List of selected options with quantities
        item_max_options: maxNumOfItemOptionAllowed from item

    Returns:
        dict: {"valid": bool, "reason": str, "total_options": int, "max_allowed": int}
    """
    total_options = sum(option.get("quantity", 0) for option in selected_options)

    if item_max_options > 0 and total_options > item_max_options:
        return {
            "valid": False,
            "reason": f"Too many options: {total_options} selected, max allowed: {item_max_options}",
            "total_options": total_options,
            "max_allowed": item_max_options,
        }
    else:
        return {
            "valid": True,
            "reason": f"Option count valid: {total_options}/{item_max_options}",
            "total_options": total_options,
            "max_allowed": item_max_options,
        }


def validate_combo_section_selections(
    combo_section: Union[ComboSection, Dict[str, Any]], selected_items: List[int]
) -> Dict[str, Any]:
    """
    Validate combo section selections against MenuSifu rules.

    API Error: Various combo-related errors based on selection rules.

    Args:
        combo_section: ComboSection model or combo section data dict
        selected_items: List of selected item IDs in this section

    Returns:
        dict: {"valid": bool, "reason": str, "rule_info": dict}
    """
    if isinstance(combo_section, ComboSection):
        selection_rule = combo_section.item_selection_rule
        min_selections = combo_section.min_num_of_selection_allowed
        max_selections = combo_section.max_num_of_selection_allowed
        allow_repeated = combo_section.allow_repeated_items
    else:
        selection_rule = combo_section.get("itemSelectionRule", 1)
        min_selections = combo_section.get("minNumOfSelectionAllowed", 1)
        max_selections = combo_section.get("maxNumOfSelectionAllowed", 1)
        allow_repeated = combo_section.get("allowRepeatedItems", False)

    selected_count = len(selected_items)
    unique_count = len(set(selected_items))

    rule_info = {
        "selection_rule": selection_rule,
        "min_required": min_selections,
        "max_allowed": max_selections,
        "allow_repeated": allow_repeated,
        "selected_count": selected_count,
        "unique_count": unique_count,
    }

    # Check repeated items if not allowed
    if not allow_repeated and selected_count != unique_count:
        return {
            "valid": False,
            "reason": "Repeated items not allowed in this section",
            "rule_info": rule_info,
        }

    # Validate based on selection rule with proper None handling
    min_sel = min_selections or 0
    max_sel = max_selections or 0

    if selection_rule == 1:  # EQUALS_TO
        if selected_count != min_sel:
            return {
                "valid": False,
                "reason": f"Must select exactly {min_sel} items, got {selected_count}",
                "rule_info": rule_info,
            }
    elif selection_rule == 2:  # MIN_NUM_LIMIT
        if selected_count < min_sel:
            return {
                "valid": False,
                "reason": f"Must select at least {min_sel} items, got {selected_count}",
                "rule_info": rule_info,
            }
    elif selection_rule == 3:  # MAX_NUM_LIMIT
        if max_sel > 0 and selected_count > max_sel:
            return {
                "valid": False,
                "reason": f"Can select at most {max_sel} items, got {selected_count}",
                "rule_info": rule_info,
            }
    elif selection_rule == 4:  # RANGE
        if selected_count < min_sel or (max_sel > 0 and selected_count > max_sel):
            return {
                "valid": False,
                "reason": f"Must select {min_sel}-{max_sel} items, got {selected_count}",
                "rule_info": rule_info,
            }

    return {"valid": True, "reason": "Selection valid", "rule_info": rule_info}


def check_item_properties(
    item: Union[SaleItem, Dict[str, Any]],
    required_properties: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Check item properties for any special requirements or restrictions.

    Args:
        item: SaleItem model or item data dict from menu response
        required_properties: Optional list of required property names

    Returns:
        dict: {"valid": bool, "reason": str, "properties": dict, "issues": list}
    """
    if isinstance(item, SaleItem):
        properties = item.properties or []
    else:
        properties = item.get("properties", [])

    property_dict = {}
    issues = []

    # Extract properties
    for prop in properties:
        if isinstance(prop, Property):
            # Pydantic Property model
            name = prop.name
            value = prop.value
            display_name = prop.display_name or name
        elif isinstance(prop, dict):
            # Dict format
            name = prop.get("name", "")
            value = prop.get("value")
            display_name = prop.get("displayName", name)
        else:
            continue

        property_dict[name] = {"value": value, "display_name": display_name}

    # Check required properties
    if required_properties:
        for req_prop in required_properties:
            if req_prop not in property_dict:
                issues.append(f"Missing required property: {req_prop}")
            elif not property_dict[req_prop]["value"]:
                issues.append(f"Required property disabled: {req_prop}")

    # Check for any restricting properties
    restricting_props = ["TEMP_UNAVAILABLE", "KITCHEN_CLOSED", "SPECIAL_ORDER"]
    for prop_name, prop_data in property_dict.items():
        if prop_name in restricting_props and prop_data["value"]:
            issues.append(f"Item restricted by property: {prop_data['display_name']}")

    return {
        "valid": len(issues) == 0,
        "reason": (
            "No property issues"
            if len(issues) == 0
            else f"Property issues: {'; '.join(issues)}"
        ),
        "properties": property_dict,
        "issues": issues,
    }


def filter_valid_menu_items(
    menu_data: Union[MenuResponse, Dict[str, Any]],
    current_time: Optional[datetime] = None,
    include_hidden: bool = False,
    include_combos: bool = True,
) -> Dict[str, Any]:
    """
    Filter menu items to return only those that are available for ordering.

    Applies all MenuSifu validation rules:
    - Time availability (CLOSING)
    - Not deleted (DELETED)
    - Not hidden (ITEM_HIDDEN)
    - In stock (SOLD_OUT, OUT_OF_STOCK)
    - Valid properties

    Args:
        menu_data: MenuResponse model or complete menu response data dict
        current_time: Current datetime for time checks
        include_hidden: Whether to include hidden items
        include_combos: Whether to include combo items

    Returns:
        dict: {"valid_items": list, "filtered_items": list, "summary": dict}
    """
    valid_items = []
    filtered_items = []

    summary = {
        "total_items": 0,
        "valid_items": 0,
        "filtered_by_time": 0,
        "filtered_by_deleted": 0,
        "filtered_by_hidden": 0,
        "filtered_by_stock": 0,
        "filtered_by_type": 0,
        "filtered_by_properties": 0,
    }

    # Handle both MenuResponse model and dict input
    if isinstance(menu_data, MenuResponse):
        groups = menu_data.groups
    else:
        groups = menu_data.get("groups", [])

    # Process all groups and categories
    for group in groups:
        if isinstance(group, MenuGroup):
            categories = group.categories
        else:
            categories = group.get("categories", [])

        for category in categories:
            if isinstance(category, Category):
                items = category.sale_items
            else:
                items = category.get("saleItems", [])

            for item in items:
                summary["total_items"] += 1

                # Apply all validation filters
                filters_passed = True
                filter_reasons = []

                # 1. Check if not deleted
                deleted_check = is_item_not_deleted(item)
                if not deleted_check["available"]:
                    filters_passed = False
                    filter_reasons.append("deleted")
                    summary["filtered_by_deleted"] += 1

                # 2. Check if not hidden (unless including hidden)
                hidden_check = is_item_not_hidden(item)
                if not include_hidden:
                    if not hidden_check["available"]:
                        filters_passed = False
                        filter_reasons.append("hidden")
                        summary["filtered_by_hidden"] += 1

                # 3. Check if in stock
                stock_check = is_item_in_stock(item)
                if not stock_check["available"]:
                    filters_passed = False
                    filter_reasons.append("out_of_stock")
                    summary["filtered_by_stock"] += 1

                # 4. Check time availability (using group hours)
                if isinstance(group, MenuGroup):
                    group_hours_data = []
                    if group.hours:
                        for h in group.hours:
                            group_hours_data.append(
                                {
                                    "fromDayOfTheWeek": h.from_day_of_the_week,
                                    "toDayOfTheWeek": h.to_day_of_the_week,
                                    "from": h.from_time,
                                    "to": h.to_time,
                                    "name": h.name,
                                }
                            )
                else:
                    group_hours_data = group.get("hours", [])

                time_check = is_item_available_by_time(
                    item, group_hours_data, current_time
                )
                if not time_check["available"]:
                    filters_passed = False
                    filter_reasons.append("time_restricted")
                    summary["filtered_by_time"] += 1

                # 5. Check item type (if excluding combos)
                item_type = (
                    item.item_type
                    if isinstance(item, SaleItem)
                    else item.get("itemType")
                )
                if not include_combos and item_type == "COMBO_SALE_ITEM":
                    filters_passed = False
                    filter_reasons.append("combo_excluded")
                    summary["filtered_by_type"] += 1

                # 6. Check properties
                property_check = check_item_properties(item)
                if not property_check["valid"]:
                    filters_passed = False
                    filter_reasons.append("properties")
                    summary["filtered_by_properties"] += 1

                # Add to appropriate list - handle both Pydantic and dict
                if isinstance(item, SaleItem):
                    item_dict = item.model_dump(by_alias=True)
                    category_id = (
                        category.id
                        if isinstance(category, Category)
                        else category.get("id")
                    )
                    category_name = (
                        category.name
                        if isinstance(category, Category)
                        else category.get("name", {})
                    )
                    group_id = (
                        group.id if isinstance(group, MenuGroup) else group.get("id")
                    )
                    group_name = (
                        group.name
                        if isinstance(group, MenuGroup)
                        else group.get("name", {})
                    )
                else:
                    item_dict = dict(item)
                    category_id = (
                        category.get("id")
                        if isinstance(category, dict)
                        else category.id
                    )
                    category_name = (
                        category.get("name", {})
                        if isinstance(category, dict)
                        else category.name
                    )
                    group_id = group.get("id") if isinstance(group, dict) else group.id
                    group_name = (
                        group.get("name", {}) if isinstance(group, dict) else group.name
                    )

                item_with_validation = {
                    **item_dict,
                    "validation": {
                        "deleted_check": deleted_check,
                        "hidden_check": (
                            hidden_check
                            if not include_hidden
                            else {"available": True, "reason": "Hidden items included"}
                        ),
                        "stock_check": stock_check,
                        "time_check": time_check,
                        "property_check": property_check,
                        "overall_valid": filters_passed,
                        "filter_reasons": filter_reasons,
                    },
                    "category_id": category_id,
                    "category_name": category_name,
                    "group_id": group_id,
                    "group_name": group_name,
                }

                if filters_passed:
                    valid_items.append(item_with_validation)
                    summary["valid_items"] += 1
                else:
                    filtered_items.append(item_with_validation)

    return {
        "valid_items": valid_items,
        "filtered_items": filtered_items,
        "summary": summary,
    }


def get_available_items_for_order(
    menu_data: Union[MenuResponse, Dict[str, Any]],
    current_time: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """
    Get a simple list of items that are available for ordering right now.

    This is a convenience function that applies all filters and returns just the valid items
    in a format suitable for creating orders.

    Args:
        menu_data: MenuResponse model or complete menu response data dict
        current_time: Current datetime for time checks

    Returns:
        list: List of items available for ordering with essential fields
    """
    result = filter_valid_menu_items(
        menu_data, current_time, include_hidden=False, include_combos=True
    )

    available_items = []
    for item in result["valid_items"]:
        # Extract essential fields for ordering
        available_items.append(
            {
                "id": item.get("id"),
                "name": item.get("name", {}),
                "itemType": item.get("itemType"),
                "price": item.get("price"),
                "basePrice": item.get("basePrice"),
                "categoryId": item.get("category_id"),
                "groupId": item.get("group_id"),
                "options": item.get("options", []),
                "comboSections": (
                    item.get("comboSections", [])
                    if item.get("itemType") == "COMBO_SALE_ITEM"
                    else None
                ),
                "maxNumOfItemOptionAllowed": item.get("maxNumOfItemOptionAllowed", 0),
            }
        )

    return available_items


def load_menu_from_json(json_data: Dict[str, Any]) -> MenuResponse:
    """
    Load menu data from JSON dict into a MenuResponse Pydantic model.

    This provides type safety and validation when working with menu data.

    Args:
        json_data: Raw JSON dict from MenuSifu API

    Returns:
        MenuResponse: Validated Pydantic model

    Raises:
        ValidationError: If the JSON data doesn't match the expected schema
    """
    return MenuResponse.model_validate(json_data)


def get_typed_available_items(
    menu_response: MenuResponse, current_time: Optional[datetime] = None
) -> List[SaleItem]:
    """
    Get available items with full type safety using Pydantic models.

    Args:
        menu_response: Validated MenuResponse model
        current_time: Current datetime for time checks

    Returns:
        list: List of SaleItem models that are available for ordering
    """
    result = filter_valid_menu_items(
        menu_response, current_time, include_hidden=False, include_combos=True
    )

    # Convert back to SaleItem models for type safety
    available_items = []
    for item_dict in result["valid_items"]:
        # Remove validation metadata before creating SaleItem
        clean_dict = {
            k: v
            for k, v in item_dict.items()
            if k
            not in [
                "validation",
                "category_id",
                "category_name",
                "group_id",
                "group_name",
            ]
        }
        try:
            sale_item = SaleItem.model_validate(clean_dict)
            available_items.append(sale_item)
        except Exception:
            # Skip items that don't validate properly
            continue

    return available_items
