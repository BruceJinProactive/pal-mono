"""
Utility functions for MenuSifu tool operations
"""

from __future__ import annotations

from typing import Any, Dict, List, Union

from .classes import DetailPrice, LocalizedName, MenuResponse, Price, Property, Size


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
