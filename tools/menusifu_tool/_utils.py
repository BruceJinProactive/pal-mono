"""
Utility functions for MenuSifu tool operations
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

if TYPE_CHECKING:
    from .classes import (
        Address,
        Customer,
        OrderCalculationRequest,
        OrderCalculationResponse,
        OrderGenerationResponse,
        OrderGenerationSelectedItem,
        OrderPrice,
    )

from utils.log import logger

from .classes import (
    Category,
    ComboDetail,
    ComboSection,
    ComboSectionForOrder,
    DetailPrice,
    ExtractedMenuSifuOrder,
    LocalizedName,
    MenuGroup,
    MenuResponse,
    MultilingualName,
    OrderGenerationSelectedItem,
    Price,
    Property,
    SaleItem,
    SelectSaleItem,
    Size,
)

# Systematic combo section mapping generated from menu data
COMBO_SECTION_MAPPINGS = {
    3170: {"section_id": 23, "section_name": "Extra Wing"},  # Extra Wings
    3290: {
        "section_id": 28,
        "section_name": "Family A.3 Persons(C)",
    },  # ~Egg Roll(3 pcs.)
    3291: {
        "section_id": 31,
        "section_name": "Family C.5 Persons",
    },  # ~House Special Fried Rice(Qt.)
    3292: {"section_id": 27, "section_name": "Family A.3 Persons(B)"},  # ~Beef Broccoli
    3293: {
        "section_id": 28,
        "section_name": "Family A.3 Persons(C)",
    },  # ~Chicken Broccoli
    3294: {
        "section_id": 30,
        "section_name": "Family B.4 Persons(S)",
    },  # ~Shrimp Roll(4 pcs.)
    3295: {
        "section_id": 30,
        "section_name": "Family B.4 Persons(S)",
    },  # ~Pork Fried Rice(Pt.)
    3296: {
        "section_id": 30,
        "section_name": "Family B.4 Persons(S)",
    },  # ~House Special Lo Mein(Qt.)
    3297: {"section_id": 31, "section_name": "Family C.5 Persons"},  # ~Gen Tso Chicken
    3298: {
        "section_id": 30,
        "section_name": "Family B.4 Persons(S)",
    },  # ~Sesame Chicken
    3299: {"section_id": 31, "section_name": "Family C.5 Persons"},  # ~Wonton Soup(Qt.)
    3300: {
        "section_id": 31,
        "section_name": "Family C.5 Persons",
    },  # ~House Special Lo Mein(Pt.)
    3301: {"section_id": 31, "section_name": "Family C.5 Persons"},  # ~Happy Family
    3304: {"section_id": 20, "section_name": "Add Sauce"},  # BBQ Sauce
    3305: {"section_id": 20, "section_name": "Add Sauce"},  # Honey Sauce
    3306: {"section_id": 20, "section_name": "Add Sauce"},  # Hot Sauce
    3307: {"section_id": 20, "section_name": "Add Sauce"},  # Garlic Sauce
    3308: {"section_id": 20, "section_name": "Add Sauce"},  # General Tso Sauce
    3309: {"section_id": 22, "section_name": "Soda Choice"},  # Coke
    3310: {"section_id": 22, "section_name": "Soda Choice"},  # Sprite
    3311: {"section_id": 22, "section_name": "Soda Choice"},  # Pepsi
    3312: {"section_id": 22, "section_name": "Soda Choice"},  # Diet Pepsi
    3313: {"section_id": 22, "section_name": "Soda Choice"},  # Diet Coke
    3314: {"section_id": 22, "section_name": "Soda Choice"},  # Ginger Ale
    3315: {"section_id": 22, "section_name": "Soda Choice"},  # Mountain Dew
    3316: {"section_id": 22, "section_name": "Soda Choice"},  # Orange Soda
    3331: {"section_id": 19, "section_name": "Rice Modify"},  # No Veggie
    3333: {"section_id": 19, "section_name": "Rice Modify"},  # No Onion
    3334: {"section_id": 19, "section_name": "Rice Modify"},  # No Pea & Carrot
    3335: {"section_id": 19, "section_name": "Rice Modify"},  # No Broccoli
    3336: {"section_id": 26, "section_name": "Modify of Rice"},  # Add Crab Sticks
    3337: {"section_id": 18, "section_name": "Dinner With"},  # Tostones
    3339: {"section_id": 18, "section_name": "Dinner With"},  # French Fries
    3355: {"section_id": 17, "section_name": "Dinner Choice"},  # .Soda
    3357: {"section_id": 21, "section_name": "Lunch With"},  # ^Steamed Rice
    3358: {"section_id": 21, "section_name": "Lunch With"},  # ^Pork Fried Rice
    3359: {"section_id": 21, "section_name": "Lunch With"},  # ^Plain Fried Rice
    3360: {"section_id": 21, "section_name": "Lunch With"},  # ^Fried Rice
    3361: {"section_id": 21, "section_name": "Lunch With"},  # ^Chicken Fried Rice
    3362: {"section_id": 21, "section_name": "Lunch With"},  # ^Veg Fried Rice
    3363: {"section_id": 21, "section_name": "Lunch With"},  # ^Beef Fried Rice
    3364: {"section_id": 21, "section_name": "Lunch With"},  # ^Shrimp Fried Rice
    3365: {"section_id": 21, "section_name": "Lunch With"},  # ^Ham Fried Rice
    3366: {"section_id": 21, "section_name": "Lunch With"},  # ^Crab Meat Fried Rice
    3367: {"section_id": 21, "section_name": "Lunch With"},  # ^House Special Fried Rice
    3368: {"section_id": 21, "section_name": "Lunch With"},  # ^Veg Lo Mein
    3369: {"section_id": 21, "section_name": "Lunch With"},  # ^Pork Lo Mein
    3370: {"section_id": 21, "section_name": "Lunch With"},  # ^Plain Lo Mein
    3371: {"section_id": 21, "section_name": "Lunch With"},  # ^Chicken Lo Mein
    3372: {"section_id": 21, "section_name": "Lunch With"},  # ^Beef Lo Mein
    3373: {"section_id": 21, "section_name": "Lunch With"},  # ^Shrimp Lo Mein
    3375: {"section_id": 21, "section_name": "Lunch With"},  # ^House Special Lo Mein
    3377: {"section_id": 18, "section_name": "Dinner With"},  # .Pork Fried Rice
    3378: {"section_id": 18, "section_name": "Dinner With"},  # .Steamed Rice
    3379: {"section_id": 18, "section_name": "Dinner With"},  # .Fried Rice
    3380: {"section_id": 18, "section_name": "Dinner With"},  # .Plain Fried Rice
    3381: {"section_id": 18, "section_name": "Dinner With"},  # .Veg Fried Rice
    3382: {"section_id": 18, "section_name": "Dinner With"},  # .Chicken Fried Rice
    3383: {"section_id": 18, "section_name": "Dinner With"},  # .Beef Fried Rice
    3384: {"section_id": 18, "section_name": "Dinner With"},  # .Ham Fried Rice
    3385: {"section_id": 18, "section_name": "Dinner With"},  # .Crab Meat Fried Rice
    3386: {"section_id": 18, "section_name": "Dinner With"},  # .Shrimp Fried Rice
    3387: {
        "section_id": 18,
        "section_name": "Dinner With",
    },  # .House Special Fried Rice
    3388: {"section_id": 18, "section_name": "Dinner With"},  # .Plain Lo Mein
    3389: {"section_id": 18, "section_name": "Dinner With"},  # .Veg Lo Mein
    3390: {"section_id": 18, "section_name": "Dinner With"},  # .Chicken Lo Mein
    3391: {"section_id": 18, "section_name": "Dinner With"},  # .Pork Lo Mein
    3392: {"section_id": 18, "section_name": "Dinner With"},  # .Beef Lo Mein
    3393: {"section_id": 18, "section_name": "Dinner With"},  # .Shrimp Lo Mein
    3394: {"section_id": 18, "section_name": "Dinner With"},  # .House Special Lo Mein
    3395: {"section_id": 17, "section_name": "Dinner Choice"},  # .Shrimp Roll
    3396: {"section_id": 17, "section_name": "Dinner Choice"},  # .Egg Roll
    3397: {"section_id": 17, "section_name": "Dinner Choice"},  # .Veg Roll
    3398: {"section_id": 17, "section_name": "Dinner Choice"},  # .Spring Roll
    3399: {"section_id": 17, "section_name": "Dinner Choice"},  # .Pizza Roll
    3400: {"section_id": 17, "section_name": "Dinner Choice"},  # .Wonton Soup
    3401: {"section_id": 17, "section_name": "Dinner Choice"},  # .Egg Drop Soup
    3425: {"section_id": 17, "section_name": "Dinner Choice"},  # Homemade Iced Tea
    3426: {"section_id": 17, "section_name": "Dinner Choice"},  # Coke
    3427: {"section_id": 17, "section_name": "Dinner Choice"},  # Sprite
    3428: {"section_id": 17, "section_name": "Dinner Choice"},  # Pepsi
    3429: {"section_id": 17, "section_name": "Dinner Choice"},  # Diet Pepsi
    3430: {"section_id": 17, "section_name": "Dinner Choice"},  # Ginger Ale
    3431: {"section_id": 17, "section_name": "Dinner Choice"},  # Diet Coke
    3432: {"section_id": 17, "section_name": "Dinner Choice"},  # Mountain Dew
    3433: {"section_id": 17, "section_name": "Dinner Choice"},  # Orange Soda
}

# Section ID to name mapping
SECTION_ID_TO_NAME = {
    17: "Dinner Choice",
    18: "Dinner With",
    19: "Rice Modify",
    20: "Add Sauce",
    21: "Lunch With",
    22: "Soda Choice",
    23: "Extra Wing",
    26: "Modify of Rice",
    27: "Family A.3 Persons(B)",
    28: "Family A.3 Persons(C)",
    29: "Family B.4 Persons(G)",
    30: "Family B.4 Persons(S)",
    31: "Family C.5 Persons",
}


def _get_combo_section_for_option(
    combo_sections: List[Dict], option_sale_item_id: int
) -> tuple[int, str]:
    """Find the combo section that contains a specific sale item ID."""
    for section in combo_sections:
        section_sale_items = section.get("comboSectionSaleItems", [])
        for sale_item in section_sale_items:
            if sale_item.get("saleItemId") == option_sale_item_id:
                return section.get("id", 0), section.get("name", {}).get(
                    "en", "Section"
                )

    # Explicitly mark as unknown to avoid mis-mapping
    available_sections = [
        f"id:{section.get('id', 0)}/name:{section.get('name', {}).get('en', 'Unknown')}"
        for section in combo_sections
    ]
    logger.info(
        f"[MenuSifuTool] combo_section_lookup: saleItemId {option_sale_item_id} not found in provided sections. "
        f"Available sections: [{', '.join(available_sections)}]"
    )
    return 0, "Unknown Section"


def validate_combo_selection_rule(
    section: Dict, selected_item_ids: List[int]
) -> Dict[str, Any]:
    """Validate combo section selection against MenuSifu rules."""
    rule = section.get("itemSelectionRule", 1)
    min_allowed = section.get("minNumOfSelectionAllowed", 0)
    max_allowed = section.get("maxNumOfSelectionAllowed", 0)
    allow_repeated = section.get("allowRepeatedItems", False)

    selected_count = len(selected_item_ids)
    unique_count = len(set(selected_item_ids))

    result = {
        "valid": True,
        "rule_type": rule,
        "min_required": min_allowed,
        "max_allowed": max_allowed,
        "selected_count": selected_count,
        "errors": [],
    }

    # Check repeated items
    if not allow_repeated and selected_count != unique_count:
        result["valid"] = False
        result["errors"].append("Repeated items not allowed in this section")

    # Apply selection rules
    if rule == 1:  # EQUALS_TO
        if selected_count != min_allowed:
            result["valid"] = False
            result["errors"].append(
                f"Must select exactly {min_allowed} items, got {selected_count}"
            )
    elif rule == 2:  # MIN_NUM_LIMIT
        if selected_count < min_allowed:
            result["valid"] = False
            result["errors"].append(
                f"Must select at least {min_allowed} items, got {selected_count}"
            )
    elif rule == 3:  # MAX_NUM_LIMIT
        if selected_count > max_allowed:
            result["valid"] = False
            result["errors"].append(
                f"Can select at most {max_allowed} items, got {selected_count}"
            )
    elif rule == 4:  # RANGE
        if selected_count < min_allowed or selected_count > max_allowed:
            result["valid"] = False
            result["errors"].append(
                f"Must select {min_allowed}-{max_allowed} items, got {selected_count}"
            )
    elif rule == 5:  # RANGE_FOR_FIXED_UNTIL_MAX
        if selected_count < min_allowed:
            result["valid"] = False
            result["errors"].append(
                f"Must select at least {min_allowed} items, got {selected_count}"
            )

    return result


def get_combo_section_price_rule(section: Dict) -> Dict[str, Any]:
    """Get price rule information for a combo section."""
    price_rule = section.get("priceRule", 1)

    rule_info = {"rule_code": price_rule, "description": ""}

    if price_rule == 1:  # ADJUSTABLE_PRICE
        rule_info["description"] = (
            "Section price is sum of selected sub-item prices and combo base price"
        )
    elif price_rule == 2:  # FIXED_UNTIL_MAX
        rule_info["description"] = (
            "Fixed price until max selections, then adjustable for excess"
        )
    elif price_rule == 3:  # FIXED_PRICE
        rule_info["description"] = "Fixed combo price, no additional charges"
    else:
        rule_info["description"] = f"Unknown price rule: {price_rule}"

    return rule_info


def find_preselected_items(section: Dict) -> List[int]:
    """Find pre-selected items in a combo section."""
    preselected = []
    section_sale_items = section.get("comboSectionSaleItems", [])

    for sale_item in section_sale_items:
        if sale_item.get("preSelected", False):
            preselected.append(sale_item.get("saleItemId"))

    return preselected


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


def create_item_lookup(menu_data: Union[MenuResponse, Dict[str, Any]]) -> dict:
    """
    Create a lookup dictionary mapping sale item IDs to their details.
    Handles both MenuResponse objects and dictionary inputs with field name compatibility.

    This includes ALL items from ALL categories, including internal ones,
    so combo sections can find their referenced items.

    Args:
        menu_data: MenuResponse object or menu dictionary containing menu data

    Returns:
        dict: Mapping of item_id -> item details with cleaned names
    """
    item_lookup = {}

    # Handle both MenuResponse objects and dictionary inputs
    if isinstance(menu_data, MenuResponse):
        groups = menu_data.groups
    else:
        groups = menu_data.get("groups", [])

    for group in groups:
        # Handle both MenuGroup objects and dictionary inputs
        if hasattr(group, "categories"):
            categories = group.categories
        elif isinstance(group, dict):
            categories = group.get("categories", [])
        else:
            continue

        for category in categories:
            # Handle both Category objects and dictionary inputs
            if hasattr(category, "sale_items"):
                sale_items = category.sale_items
                category_name_en = category.name.en or ""
                category_name_zh = category.name.zh_cn or ""
                category_name = category_name_en
            elif isinstance(category, dict):
                # Handle both camelCase and snake_case for dictionary inputs
                sale_items = category.get("saleItems", []) or category.get(
                    "sale_items", []
                )
                cat_name = category.get("name", {})
                if isinstance(cat_name, dict):
                    category_name_en = cat_name.get("en", "")
                    category_name_zh = cat_name.get("zh-cn", "")
                else:
                    category_name_en = str(cat_name)
                    category_name_zh = ""
                category_name = category_name_en
            else:
                continue

            for item in sale_items:
                # Handle both SaleItem objects and dictionary inputs
                if hasattr(item, "name"):
                    # Object access
                    item_id = item.id
                    item_name = item.name
                    clean_name_en = clean_item_name(
                        item_name.en if item_name.en else ""
                    )
                    clean_name_zh = clean_item_name(
                        item_name.zh_cn if item_name.zh_cn else ""
                    )
                    item_type = getattr(item, "item_type", None) or getattr(
                        item, "itemType", "REGULAR_ITEM"
                    )
                    price = item.price
                    base_price = getattr(item, "base_price", None) or getattr(
                        item, "basePrice", None
                    )
                    out_of_stock = getattr(item, "out_of_stock", False) or getattr(
                        item, "outOfStock", False
                    )
                    hidden_item = getattr(item, "hidden_item", False) or getattr(
                        item, "hiddenItem", False
                    )
                elif isinstance(item, dict):
                    # Dictionary access with field name compatibility
                    item_id = item.get("id")
                    item_name = item.get("name", {})
                    if isinstance(item_name, dict):
                        clean_name_en = clean_item_name(item_name.get("en", ""))
                        clean_name_zh = clean_item_name(item_name.get("zh-cn", ""))
                    else:
                        clean_name_en = clean_item_name(
                            str(item_name) if item_name else ""
                        )
                        clean_name_zh = ""
                    item_type = get_field_value(
                        item, "itemType", "item_type", "REGULAR_ITEM"
                    )
                    price = item.get("price")
                    base_price = get_field_value(item, "basePrice", "base_price")
                    out_of_stock = get_field_value(
                        item, "outOfStock", "out_of_stock", False
                    )
                    hidden_item = get_field_value(
                        item, "hiddenItem", "hidden_item", False
                    )
                else:
                    continue

                if item_id:
                    item_lookup[item_id] = {
                        "name_en": clean_name_en,
                        "name_zh": clean_name_zh,
                        "item_type": item_type,
                        "category": category_name,
                        "price": price,
                        "base_price": base_price,
                        "out_of_stock": out_of_stock,
                        "hidden_item": hidden_item,
                        "from_internal_category": is_internal_category(
                            category_name_en, category_name_zh
                        ),
                    }

    return item_lookup


def generate_bilingual_menu_content(
    menu_data: Union[MenuResponse, Dict[str, Any]], user_friendly: bool = False
) -> str:
    """
    Generate bilingual menu content based on official MenuSifu API specs.
    Supports both MenuResponse objects and dictionary inputs.

    Features implemented according to API documentation:
    - Cleans item names by removing ^ or ~ prefixes
    - Handles hidden items and categories (skips them by default)
    - Shows out of stock status
    - Detailed combo information with proper selection rules
    - Bilingual support for all text elements
    - Group hours and descriptions
    - Required category marking
    - Combo type and pricing rule information

    Args:
        menu_data: MenuResponse object or dictionary containing menu data
        user_friendly: If True, excludes technical IDs and includes hidden items

    Returns:
        str: Bilingual menu content with comprehensive combo details
    """
    lines = []

    # Handle both MenuResponse objects and dictionary inputs
    if isinstance(menu_data, MenuResponse):
        menu_name = menu_data.name
        groups = menu_data.groups
    else:
        menu_name = menu_data.get("name", {})
        groups = menu_data.get("groups", [])

    # Create item lookup for combo resolution
    item_lookup = create_item_lookup(menu_data)

    # Menu title - cleaned according to API specs
    if hasattr(menu_name, "en"):
        menu_name_en = clean_item_name(menu_name.en if menu_name.en else "Menu")
        menu_name_zh = clean_item_name(menu_name.zh_cn if menu_name.zh_cn else "")
    elif isinstance(menu_name, dict):
        menu_name_en = clean_item_name(menu_name.get("en", "Menu"))
        menu_name_zh = clean_item_name(menu_name.get("zh-cn", ""))
    else:
        menu_name_en = "Menu"
        menu_name_zh = ""

    if menu_name_zh:
        lines.append(f"{menu_name_en} / {menu_name_zh}")
    else:
        lines.append(menu_name_en)
    lines.append("=" * len(lines[-1]))
    lines.append("")

    # Process groups and categories according to API specs
    for group in groups:
        # Handle both MenuGroup objects and dictionary inputs
        if hasattr(group, "name"):
            # Group name - cleaned for object access
            group_name_en = clean_item_name(group.name.en if group.name.en else "")
            group_name_zh = clean_item_name(
                group.name.zh_cn if group.name.zh_cn else ""
            )
            categories = group.categories
            group_desc = getattr(group, "description", "")
            group_hours = getattr(group, "hours", [])
        elif isinstance(group, dict):
            # Group name - cleaned for dictionary access
            group_name_dict = group.get("name", {})
            if isinstance(group_name_dict, dict):
                group_name_en = clean_item_name(group_name_dict.get("en", ""))
                group_name_zh = clean_item_name(group_name_dict.get("zh-cn", ""))
            else:
                group_name_en = clean_item_name(str(group_name_dict))
                group_name_zh = ""
            categories = group.get("categories", [])
            group_desc = group.get("description", "")
            group_hours = group.get("hours", [])
        else:
            continue

        if group_name_en:
            if group_name_zh:
                group_title = f"{group_name_en} / {group_name_zh}"
            else:
                group_title = group_name_en

            lines.append(f"# {group_title}")

            # Compact group info on single line
            group_info = []
            if group_desc:
                group_info.append(group_desc)

            # Simplified hours
            if group_hours:
                hour_texts = []
                for hour in group_hours:
                    # Handle both object and dictionary hour access
                    if hasattr(hour, "name"):
                        hour_name = hour.name
                        from_time = getattr(
                            hour, "from_time", getattr(hour, "from", "Unknown")
                        )
                        to_time = getattr(
                            hour, "to_time", getattr(hour, "to", "Unknown")
                        )
                    elif isinstance(hour, dict):
                        hour_name = hour.get("name", "")
                        from_time = hour.get("from", hour.get("from_time", "Unknown"))
                        to_time = hour.get("to", hour.get("to_time", "Unknown"))
                    else:
                        continue

                    if hour_name and from_time != "Unknown" and to_time != "Unknown":
                        hour_texts.append(f"{from_time}-{to_time}")
                if hour_texts:
                    group_info.append(f"Hours: {' | '.join(hour_texts)}")

            if group_info:
                lines.append(f"*{' | '.join(group_info)}*")

            lines.append("")

        # Process categories
        for category in categories:
            # Handle both Category objects and dictionary inputs for hidden check
            if hasattr(category, "hidden_category"):
                is_hidden_category = getattr(category, "hidden_category", False)
            elif isinstance(category, dict):
                is_hidden_category = get_field_value(
                    category, "hiddenCategory", "hidden_category", False
                )
            else:
                continue

            # Skip hidden categories unless user_friendly mode
            if is_hidden_category and not user_friendly:
                continue

            # Handle both Category objects and dictionary inputs for name/items
            if isinstance(category, dict):
                # Category name - cleaned for dictionary access
                cat_name_dict = category.get("name", {})
                if isinstance(cat_name_dict, dict):
                    cat_name_en = clean_item_name(cat_name_dict.get("en", ""))
                    cat_name_zh = clean_item_name(cat_name_dict.get("zh-cn", ""))
                else:
                    cat_name_en = clean_item_name(str(cat_name_dict))
                    cat_name_zh = ""
                sale_items = category.get("saleItems", []) or category.get(
                    "sale_items", []
                )
                category_desc = category.get("description", "")
                require_category = get_field_value(
                    category, "requireCategory", "require_category", False
                )
            elif hasattr(category, "name"):
                # Category name - cleaned for object access
                cat_name_en = clean_item_name(
                    category.name.en if category.name.en else ""
                )
                cat_name_zh = clean_item_name(
                    category.name.zh_cn if category.name.zh_cn else ""
                )
                sale_items = category.sale_items
                category_desc = category.description
                require_category = getattr(category, "require_category", False)
            else:
                continue

            # Skip internal system categories (like "Combo Items DON'T DELETE")
            if is_internal_category(cat_name_en, cat_name_zh):
                continue

            # First, collect all valid items for this category
            category_lines = []

            # Process items to see if any are valid
            for item in sale_items:

                # Handle both SaleItem objects and dictionary inputs
                if hasattr(item, "name"):
                    # Object access
                    item_name_obj = item.name
                    item_name_en = clean_item_name(
                        item_name_obj.en if item_name_obj.en else ""
                    )
                    item_name_zh = clean_item_name(
                        item_name_obj.zh_cn if item_name_obj.zh_cn else ""
                    )
                    item_type = item.item_type
                    is_hidden_item = getattr(item, "hidden_item", False)
                    item_price = item.price
                    base_price = getattr(item, "base_price", None) or getattr(
                        item, "basePrice", None
                    )
                    combo_sections = getattr(item, "combo_sections", None) or getattr(
                        item, "comboSections", []
                    )
                    combo_type = getattr(item, "combo_type", None) or getattr(
                        item, "comboType", None
                    )
                elif isinstance(item, dict):
                    # Dictionary access
                    item_name_dict = item.get("name", {})
                    if isinstance(item_name_dict, dict):
                        item_name_en = clean_item_name(item_name_dict.get("en", ""))
                        item_name_zh = clean_item_name(item_name_dict.get("zh-cn", ""))
                    else:
                        item_name_en = clean_item_name(
                            str(item_name_dict) if item_name_dict else ""
                        )
                        item_name_zh = ""
                    item_type = get_field_value(
                        item, "itemType", "item_type", "REGULAR_ITEM"
                    )
                    is_hidden_item = get_field_value(
                        item, "hiddenItem", "hidden_item", False
                    )
                    item_price = item.get("price")
                    base_price = get_field_value(item, "basePrice", "base_price")
                    combo_sections = get_field_value(
                        item, "comboSections", "combo_sections", []
                    )
                    combo_type = get_field_value(item, "comboType", "combo_type")
                else:
                    continue

                # Get prices (filtered for zero prices)
                prices = _format_prices(item)

                # Skip items with no valid prices (zero prices filtered out)
                # Exception: Don't skip combo items that might have zero prices
                if not prices and item_type != "COMBO_SALE_ITEM":
                    continue

                # Skip hidden items unless user_friendly mode
                if is_hidden_item and not user_friendly:
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
                    if item_type == "COMBO_SALE_ITEM" and combo_sections:
                        combo_info = "COMBO"
                        if combo_type == 1:
                            combo_info += " (Fixed)"
                        elif combo_type == 2:
                            combo_info += " (Flexible)"

                        # Use the base_price extracted earlier
                        if base_price:
                            try:
                                numeric_base_price = float(base_price)
                                numeric_item_price = (
                                    float(item_price) if item_price is not None else 0
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
                        for i, section in enumerate(combo_sections):
                            # Check section availability first
                            section_availability = check_combo_section_availability(
                                section, item_lookup
                            )

                            section_items = []
                            section_pre_selected = []
                            section_unavailable_items = []

                            # Handle both camelCase and snake_case field names
                            combo_items = getattr(
                                section, "combo_section_sale_items", None
                            ) or getattr(section, "comboSectionSaleItems", [])
                            if combo_items:
                                for combo_item in combo_items:
                                    # Handle both field naming conventions
                                    sale_item_id = getattr(
                                        combo_item, "sale_item_id", None
                                    ) or getattr(combo_item, "saleItemId", None)
                                    item_details = (
                                        item_lookup.get(sale_item_id, {})
                                        if sale_item_id
                                        else {}
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
                                        elif item_name_zh:
                                            dish_name = item_name_zh
                                        else:
                                            # Skip items with no name instead of showing ID
                                            continue
                                    else:
                                        # Skip items not found in lookup - don't show ID references
                                        continue

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

                                        # Handle both field naming conventions for pre_selected
                                        is_pre_selected = getattr(
                                            combo_item, "pre_selected", False
                                        ) or getattr(combo_item, "preSelected", False)
                                        if is_pre_selected:
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
                            # Handle both field naming conventions
                            rule = getattr(
                                section, "item_selection_rule", None
                            ) or getattr(section, "itemSelectionRule", None)
                            min_sel = (
                                getattr(section, "min_num_of_selection_allowed", None)
                                or getattr(section, "minNumOfSelectionAllowed", 0)
                                or 0
                            )
                            max_sel = (
                                getattr(section, "max_num_of_selection_allowed", None)
                                or getattr(section, "maxNumOfSelectionAllowed", 0)
                                or 0
                            )
                            allow_repeated = getattr(
                                section, "allow_repeated_items", False
                            ) or getattr(section, "allowRepeatedItems", False)

                            selection_rule = get_selection_rule_description(
                                rule or 0, min_sel, max_sel, allow_repeated
                            )
                            # Handle both field naming conventions
                            price_rule = getattr(
                                section, "price_rule", None
                            ) or getattr(section, "priceRule", None)
                            pricing_rule = get_price_rule_description(price_rule or 0)

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
                                f"  Issues: {', '.join(combo_unavailable_sections)}"
                            )
                        elif combo_has_issues:
                            category_lines.append("  Some items sold out")

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
                if category_desc:
                    category_details.append(category_desc)
                if require_category:
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


# =============================================================================
# ORDER PROCESSING UTILITY FUNCTIONS
# =============================================================================


def build_order_price_from_calculation(
    calc_response: "OrderCalculationResponse",
) -> "OrderPrice":
    """
    Convert OrderCalculationResponse price data to OrderPrice for order generation.

    Args:
        calc_response: Response from order calculation API

    Returns:
        OrderPrice object for order generation request
    """
    from decimal import Decimal

    from .classes import ChargeObjectInfo, OrderPrice, TaxInfo

    # Build charge objects from calculation response
    charge_obj_list = []
    if calc_response.charge_obj:
        for charge in calc_response.charge_obj:
            charge_info = ChargeObjectInfo(
                charge=charge.charge or Decimal("0"),
                chargeIsPer=getattr(charge, "charge_is_per", None),
                chargeRate=getattr(charge, "charge_rate", None),
                type=getattr(charge, "type", None),
            )
            charge_obj_list.append(charge_info)

    # Build taxes from order tax detail
    taxes_list = []
    if calc_response.order_tax_detail:
        for tax_id, tax_detail in calc_response.order_tax_detail.items():
            tax_info = TaxInfo(
                name=f"Tax {tax_id}",
                value=tax_detail.tax_amount or Decimal("0"),
                rate=getattr(tax_detail, "tax_rate", None) or Decimal("0"),
            )
            taxes_list.append(tax_info)

    return OrderPrice(
        subtotal=calc_response.order_subtotal or Decimal("0"),
        total=calc_response.order_total or Decimal("0"),
        discount=calc_response.order_discount or Decimal("0"),
        onlineFee=getattr(calc_response, "online_fee", None) or Decimal("0"),
        deliveryFee=getattr(calc_response, "delivery_fee", None) or Decimal("0"),
        charge=calc_response.order_charge or Decimal("0"),
        chargeObj=charge_obj_list,
        tips=getattr(calc_response, "total_tips", None) or Decimal("0"),
        taxTotal=calc_response.order_tax_total or Decimal("0"),
        taxes=taxes_list,
        chargeName=calc_response.charge_name or "",
        discountTotalCrm=getattr(calc_response, "discount_total_crm", None)
        or Decimal("0"),
        rounding=calc_response.rounding or Decimal("0"),
    )


def build_selected_items_from_calculation_with_menu_data(
    calc_request: "OrderCalculationRequest",
    menu_data: Optional[Dict[str, Any]] = None,
) -> List["OrderGenerationSelectedItem"]:
    """
    Convert OrderCalculationRequest items to OrderGenerationSelectedItem list with proper combo section mapping.

    Args:
        calc_request: Original calculation request with selected items
        menu_data: Full menu data to lookup combo sections properly

    Returns:
        List of OrderGenerationSelectedItem objects with correct combo mappings
    """
    selected_items = []

    # Create item lookup for combo section resolution if menu_data provided
    # Note: item_lookup is created but not used in current implementation
    if menu_data:
        create_item_lookup(
            menu_data
        )  # Create but don't store - not used in current flow

    for item in calc_request.selected_items:
        # Convert options to comboDetail if they exist
        combo_detail = None
        if item.options and len(item.options) > 0:
            # Find the item in menu data to get its combo sections
            combo_sections = []
            if menu_data:
                combo_sections = _find_combo_sections_for_item(menu_data, item.id)

            if combo_sections:
                # Group options by their actual combo sections
                section_map = {}
                combo_options = []
                additional_options = []

                for option in item.options:
                    section_id, section_name = _get_combo_section_for_option(
                        combo_sections, option.id or 0
                    )

                    # If any option maps to section_id == 0 (unknown), fall back to regular builder
                    if section_id == 0:
                        # Early return - fallback to build_selected_items_from_calculation
                        return build_selected_items_from_calculation(calc_request)

                    # Check if this is a real combo option vs an additional option
                    if option.id is not None and section_id != 0:
                        # This is a combo option
                        combo_options.append(option)

                        if section_id not in section_map:
                            section_map[section_id] = {
                                "id": section_id,
                                "name": section_name,
                                "items": [],
                            }

                        select_item = SelectSaleItem(
                            saleItemId=option.id or 0,
                            quantity=1,
                            name=option.name,
                            nameMultilingual=option.name_multilingual,
                            price=option.price,
                            detailPriceId="",
                        )
                        section_map[section_id]["items"].append(select_item)
                    else:
                        # This is an additional option/note
                        additional_options.append(option)

                # Build combo sections
                combo_sections_list = []
                for section_data in section_map.values():
                    combo_section = ComboSectionForOrder(
                        id=section_data["id"],
                        name=section_data["name"],
                        nameMultilingual=None,  # Will be populated from menu data if available
                        selectSaleItems=section_data["items"],
                    )
                    combo_sections_list.append(combo_section)

                combo_detail = ComboDetail(comboSections=combo_sections_list)

            else:
                # No combo sections found in menu data - fallback to build_selected_items_from_calculation
                return build_selected_items_from_calculation(calc_request)

        # Convert additional options to OrderItemOptionNote format if any
        converted_options = None
        additional_options = []

        if item.options and combo_detail is None:
            # For non-combo items, all options remain as options
            additional_options = item.options
        # If we processed combo options above, additional_options is already set

        if additional_options:
            from .classes import OrderItemOptionNote

            converted_options = []
            for option in additional_options:
                is_real_option = option.id is not None
                # Normalize sectionName to MultilingualName
                _raw_section_name = getattr(option, "section_name", None)
                option_note = OrderItemOptionNote(
                    sectionId=getattr(option, "section_id", None),
                    sectionName=(
                        _raw_section_name
                        if isinstance(_raw_section_name, MultilingualName)
                        else (
                            MultilingualName(
                                en=_raw_section_name, **{"zh-cn": None, "French": None}
                            )
                            if _raw_section_name
                            else None
                        )
                    ),
                    id=option.id,
                    detailPriceId=None,
                    optionPrice=(
                        Decimal(str(option.price))
                        if (option.price and is_real_option)
                        else None
                    ),
                    name=option.name if not is_real_option else None,
                    nameMultilingual=getattr(option, "name_multilingual", None),
                    price=(
                        Decimal(str(option.price))
                        if (option.price and not is_real_option)
                        else Decimal("0")
                    ),
                    priceOriginal=None,
                    quantity=option.quantity or 1,
                    checked=getattr(option, "checked", True),
                    isOpenOption=getattr(option, "is_open_option", False),
                )
                converted_options.append(option_note)

        # Build the selected item for generation
        generation_item = OrderGenerationSelectedItem(
            id=item.id,
            saleItemId=item.id,
            quantity=item.quantity,
            itemType=item.item_type,
            price=item.price,
            displayPrice=item.price,
            name=item.name,
            nameMultilingual=item.name_multilingual,
            categoryId=item.category_id,
            options=converted_options,
            comboDetail=combo_detail,
        )
        selected_items.append(generation_item)

    return selected_items


def _find_combo_sections_for_item(
    menu_data: Dict[str, Any], item_id: int
) -> List[Dict]:
    """Find combo sections for a specific item ID in menu data."""
    for group in menu_data.get("groups", []):
        for category in group.get("categories", []):
            for item in category.get("saleItems", []):
                if (
                    item.get("id") == item_id
                    and item.get("itemType") == "COMBO_SALE_ITEM"
                ):
                    return item.get("comboSections", [])
    return []


def build_selected_items_from_calculation(
    calc_request: "OrderCalculationRequest",
) -> List["OrderGenerationSelectedItem"]:
    """
    Convert OrderCalculationRequest items to OrderGenerationSelectedItem list.
    Handles flexible combo structures including items with both comboDetail and options.

    Args:
        calc_request: Original calculation request with selected items

    Returns:
        List of OrderGenerationSelectedItem objects
    """
    from .classes import MultilingualName

    selected_items = []

    for item in calc_request.selected_items:
        # For combo items, separate options into combo selections vs additional options
        combo_detail = None
        remaining_options = []

        if item.item_type == "COMBO_SALE_ITEM" and item.options:
            # Group options by type - combo selections vs additional options
            combo_options = []
            additional_options = []

            for option in item.options:
                # Use systematic mapping based on option ID (if available)
                if option.id and option.id in COMBO_SECTION_MAPPINGS:
                    combo_options.append(option)
                else:
                    # Additional options like special requests, add-ons without mapped IDs
                    additional_options.append(option)

            # Build combo detail from combo selections if any exist
            if combo_options:
                # Group options by combo section type
                section_groups = {}

                for option in combo_options:
                    # Get section info from systematic mapping
                    if option.id and option.id in COMBO_SECTION_MAPPINGS:
                        section_info = COMBO_SECTION_MAPPINGS[option.id]
                        section_id = section_info["section_id"]
                        section_name = section_info["section_name"]
                    else:
                        # Fallback for unmapped items (shouldn't happen with systematic mapping)
                        section_id = 21
                        section_name = "Lunch With"

                    # Group by section
                    if section_id not in section_groups:
                        section_groups[section_id] = {"name": section_name, "items": []}

                    # Create MultilingualName with proper field names
                    option_multilingual = MultilingualName(
                        en=option.name, **{"zh-cn": None, "French": None}
                    )

                    select_item = SelectSaleItem(
                        saleItemId=option.id or 0,
                        quantity=1,
                        name=option.name,
                        nameMultilingual=option_multilingual,
                        price=(
                            Decimal(str(option.price)) if option.price else Decimal("0")
                        ),
                        detailPriceId="",
                    )
                    section_groups[section_id]["items"].append(select_item)

                # Create combo sections for each group
                combo_sections_list = []
                for section_id, group_data in section_groups.items():
                    section_multilingual = MultilingualName(
                        en=group_data["name"], **{"zh-cn": group_data["name"]}
                    )

                    combo_section = ComboSectionForOrder(
                        id=section_id,
                        name=group_data["name"],
                        nameMultilingual=section_multilingual,
                        selectSaleItems=group_data["items"],
                    )
                    combo_sections_list.append(combo_section)

                combo_detail = ComboDetail(comboSections=combo_sections_list)

            # Keep additional options for the options field
            remaining_options = additional_options

        elif item.item_type == "SALE_ITEM" and item.options:
            # For regular items, all options remain as options
            remaining_options = item.options

        # Convert remaining options to OrderItemOptionNote format if any
        converted_options = None
        if remaining_options:
            from .classes import OrderItemOptionNote

            converted_options = []
            for option in remaining_options:
                is_real_option = option.id is not None
                option_note = OrderItemOptionNote(
                    sectionId=getattr(option, "section_id", None),
                    sectionName=getattr(option, "section_name", None),
                    id=option.id,
                    detailPriceId=None,
                    optionPrice=(
                        Decimal(str(option.price))
                        if (option.price and is_real_option)
                        else None
                    ),
                    name=option.name if not is_real_option else None,
                    nameMultilingual=getattr(option, "name_multilingual", None),
                    price=(
                        Decimal(str(option.price))
                        if (option.price and not is_real_option)
                        else Decimal("0")
                    ),
                    priceOriginal=None,
                    quantity=option.quantity or 1,
                    checked=getattr(option, "checked", True),
                    isOpenOption=getattr(option, "is_open_option", False),
                )
                converted_options.append(option_note)

        # Create item MultilingualName with proper field names
        item_multilingual = MultilingualName(
            en=item.name, **{"zh-cn": None, "French": None}
        )

        # Build the selected item for generation (supporting both comboDetail and options)
        generation_item = OrderGenerationSelectedItem(
            id=item.id,
            saleItemId=item.id,
            quantity=item.quantity,
            itemType=item.item_type,
            price=item.price,
            displayPrice=item.price,
            name=item.name,
            nameMultilingual=item_multilingual,
            categoryId=item.category_id,
            options=converted_options,  # Can coexist with comboDetail
            comboDetail=combo_detail,  # May be None for non-combo items
        )
        selected_items.append(generation_item)

    return selected_items


def build_customer_info(
    email: str,
    first_name: str,
    last_name: str = "",
    country_code: str = "+1",
    phone_number: str = "",
) -> "Customer":
    """
    Build Customer object for order generation.

    Args:
        email: Customer email
        first_name: Customer first name
        last_name: Customer last name (optional)
        country_code: Phone country code (default +1)
        phone_number: Phone number without country code

    Returns:
        Customer object
    """
    from .classes import Customer, Phone

    phone = Phone(countryCode=country_code, number=phone_number)

    return Customer(email=email, firstName=first_name, lastName=last_name, phone=phone)


def build_address_info(
    address1: str = "",
    address2: str = "",
    city: str = "",
    state: str = "",
    zip_code: str = "",
) -> "Address":
    """
    Build Address object for order generation.

    Args:
        address1: Primary address line
        address2: Secondary address line
        city: City
        state: State/Province
        zip_code: ZIP/Postal code

    Returns:
        Address object
    """
    from .classes import Address

    return Address(
        address1=address1, address2=address2, city=city, state=state, zipCode=zip_code
    )


def validate_order_data(
    customer_email: str,
    customer_first_name: str,
    phone_number: str,
    selected_items: List[Dict[str, Any]],
) -> Dict[str, List[str]]:
    """
    Validate order data before API submission.

    Args:
        customer_email: Customer email
        customer_first_name: Customer first name
        phone_number: Customer phone number
        selected_items: List of selected items

    Returns:
        Dictionary with validation errors by field
    """
    errors = {}

    # Email validation
    if not customer_email or "@" not in customer_email:
        errors.setdefault("customer_email", []).append(
            "Valid email address is required"
        )

    # Name validation
    if not customer_first_name or len(customer_first_name.strip()) < 1:
        errors.setdefault("customer_first_name", []).append("First name is required")

    # Phone validation (basic)
    if (
        phone_number
        and not phone_number.replace("+", "")
        .replace("-", "")
        .replace(" ", "")
        .isdigit()
    ):
        errors.setdefault("phone_number", []).append(
            "Phone number must contain only digits, +, -, and spaces"
        )

    # Items validation
    if not selected_items:
        errors.setdefault("selected_items", []).append(
            "At least one item must be selected"
        )

    for i, item in enumerate(selected_items):
        if not item.get("id"):
            errors.setdefault("selected_items", []).append(
                f"Item {i+1}: ID is required"
            )
        quantity = item.get("quantity", 0)
        if not quantity or quantity <= 0:
            errors.setdefault("selected_items", []).append(
                f"Item {i+1}: Quantity must be greater than 0"
            )

    return errors


def format_phone_number(
    phone: str, default_country_code: str = "+1"
) -> tuple[str, str]:
    """
    Format phone number into country code and number parts.

    Args:
        phone: Full phone number (may include country code)
        default_country_code: Default country code if none provided

    Returns:
        Tuple of (country_code, phone_number)
    """
    if not phone:
        return default_country_code, ""

    # Clean the phone number
    clean_phone = (
        phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    )

    # If starts with +, extract country code
    if clean_phone.startswith("+"):
        # First, try known country codes with expected lengths
        known_codes = {
            "+1": 10,  # North America: +1 + 10 digits = 12 total
            "+86": 8,  # China: +86 + 8+ digits
            "+33": 8,  # France: +33 + 8+ digits
            "+44": 8,  # UK: +44 + 8+ digits
            "+49": 8,  # Germany: +49 + 8+ digits
            "+81": 8,  # Japan: +81 + 8+ digits
            "+82": 8,  # South Korea: +82 + 8+ digits
        }

        for country_code, min_remaining in known_codes.items():
            if clean_phone.startswith(country_code):
                remaining = clean_phone[len(country_code) :]
                if len(remaining) >= min_remaining and (
                    country_code == "+1"
                    and len(remaining) == 10
                    or country_code != "+1"
                ):
                    return country_code, remaining

        # Fallback: try generic country code lengths (+ plus 1-3 digits)
        for code_len in range(2, 5):  # +X, +XX, +XXX
            if code_len < len(clean_phone):
                country_code = clean_phone[:code_len]
                remaining = clean_phone[code_len:]
                # Return if remaining has plausible length (>=8 digits)
                if len(remaining) >= 8:
                    return country_code, remaining

    # No country code provided, use default
    return default_country_code, clean_phone


def extract_order_summary(order_response: "OrderGenerationResponse") -> Dict[str, Any]:
    """
    Extract key information from order generation response for display/logging.

    Args:
        order_response: Response from order generation API

    Returns:
        Dictionary with key order information
    """
    if not order_response or not order_response.order:
        return {"error": "No order data in response"}

    order = order_response.order

    # Handle price safely for dict or Pydantic model
    _price_obj = getattr(order, "price", None)
    if isinstance(_price_obj, dict):
        price_info = _price_obj
    else:
        try:
            price_info = _price_obj.model_dump(by_alias=True) if _price_obj else {}
        except Exception:
            price_info = {}

    summary = {
        "order_id": getattr(order, "_id", None),
        "order_number": getattr(order, "orderNumber", "N/A"),
        "status": getattr(order, "status", None),
        "kitchen_status": getattr(order, "kitchen_status", None),
        "payment_summary": getattr(order, "payment_summary", "N/A"),
        "total_amount": float(price_info.get("total", 0)) if price_info else 0,
        "subtotal": float(price_info.get("subtotal", 0)) if price_info else 0,
        "tax_total": float(price_info.get("taxTotal", 0)) if price_info else 0,
        "tips": float(price_info.get("tips", 0)) if price_info else 0,
        "order_type": getattr(order, "type", "N/A"),
        "customer_email": (
            getattr(getattr(order, "customer", None), "email", None)
            if not isinstance(getattr(order, "customer", None), dict)
            else getattr(order, "customer", {}).get("email", "N/A")
        )
        or "N/A",
        "customer_name": (
            (
                f"{getattr(getattr(order, 'customer', None), 'firstName', '')} {getattr(getattr(order, 'customer', None), 'lastName', '')}".strip()
                if not isinstance(getattr(order, "customer", None), dict)
                else f"{getattr(order, 'customer', {}).get('firstName','')} {getattr(order, 'customer', {}).get('lastName','')}".strip()
            )
            or "N/A"
        ),
        "transaction_id": getattr(order, "transaction_id", "N/A"),
        "successful": getattr(order_response, "successful", True),
        "payment_url": getattr(order_response, "payment_url", None),
        "created_at": getattr(order, "create_at", None),
        "item_count": len(getattr(order, "orderItems", [])),
    }

    return summary


def handle_api_error(error_response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse and standardize API error responses.

    Args:
        error_response: Raw error response from API

    Returns:
        Standardized error information
    """
    error_info = {
        "error_type": "api_error",
        "message": "Unknown error occurred",
        "details": {},
        "is_retryable": False,
    }

    if isinstance(error_response, dict):
        # Standard error message
        if "message" in error_response:
            error_info["message"] = error_response["message"]

        # Check for specific error types
        message = error_response.get("message", "").lower()

        if "price validate error" in message:
            error_info["error_type"] = "price_validation"
            error_info["message"] = (
                "Order price validation failed - check item prices and calculations"
            )

        elif "phone number is not available" in message:
            error_info["error_type"] = "phone_validation"
            error_info["message"] = "Invalid phone number format"

        elif "sold out" in message or "out of stock" in message:
            error_info["error_type"] = "inventory"
            error_info["is_retryable"] = True

        elif "merchant" in message and ("not found" in message or "invalid" in message):
            error_info["error_type"] = "merchant_validation"

        elif "unauthorized" in message or "access" in message:
            error_info["error_type"] = "authorization"

        # Extract additional details
        error_info["details"] = {
            k: v for k, v in error_response.items() if k != "message"
        }

    return error_info


def calculate_order_totals(
    items: List[Dict[str, Any]],
    tax_rate: float = 0.1,
    delivery_fee: float = 0.0,
    convenience_fee: float = 0.0,
    tips: float = 0.0,
) -> Dict[str, float]:
    """
    Calculate order totals from items and fees.

    Args:
        items: List of items with price and quantity
        tax_rate: Tax rate (default 10%)
        delivery_fee: Delivery fee
        convenience_fee: Convenience fee
        tips: Tips amount

    Returns:
        Dictionary with calculated totals
    """

    # Calculate subtotal
    subtotal = Decimal("0")
    for item in items:
        item_price = Decimal(str(item.get("price", 0)))
        quantity = int(item.get("quantity", 1))
        subtotal += item_price * quantity

    # Calculate tax
    tax_amount = subtotal * Decimal(str(tax_rate))

    # Calculate total before rounding
    total_before_rounding = (
        subtotal
        + tax_amount
        + Decimal(str(delivery_fee))
        + Decimal(str(convenience_fee))
        + Decimal(str(tips))
    )

    # Apply rounding to nearest cent
    total = total_before_rounding.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    rounding = total - total_before_rounding

    return {
        "subtotal": float(subtotal),
        "tax_amount": float(tax_amount),
        "delivery_fee": delivery_fee,
        "convenience_fee": convenience_fee,
        "tips": tips,
        "total_before_rounding": float(total_before_rounding),
        "total": float(total),
        "rounding": float(rounding),
    }


def convert_extracted_order_to_dict(
    extracted_order: ExtractedMenuSifuOrder,
) -> List[Dict[str, Any]]:
    """
    Convert ExtractedMenuSifuOrder to internal dict format for processing.
    Properly handles combo items vs regular items with modifiers.

    Args:
        extracted_order: Extracted order from LLM

    Returns:
        List of item dictionaries in internal format
    """
    processed_items = []
    for item in extracted_order.items:
        # Convert modifiers to options format
        # The system will later convert these to comboDetail for combo items
        options_list = []
        for modifier in item.modifiers:
            option_dict = {
                "id": modifier.id,
                "name": modifier.name,
                "price": modifier.price,
                "quantity": modifier.quantity,
                "checked": modifier.checked,
                "name_multilingual": None,  # Will be populated later if needed
                "section_name": None,  # Will be determined based on item type
            }
            options_list.append(option_dict)

        item_dict = {
            "id": item.item_id,
            "item_id": item.item_id,
            "sale_item_id": item.item_id,  # For MenuSifu: always same as item_id
            "name": item.item_name,
            "quantity": item.quantity,
            "price": item.price,
            "display_price": item.display_price,
            "item_type": item.item_type,
            "category_id": item.category_id,
            "special_notes": item.special_notes or "",
            "options": options_list,  # Modifiers converted to options - will become comboDetail for combo items
        }
        processed_items.append(item_dict)

    return processed_items


def safe_convert_item_fields(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Safely convert item fields with proper validation and defaults.

    Args:
        item: Raw item dictionary from order data

    Returns:
        Dict with safely converted fields

    Raises:
        ValueError: If required fields are missing
    """
    logger.debug(f"[safe_convert_item_fields] Processing item: {item}")

    # Extract raw ID from item
    raw_id = item.get("id") or item.get("item_id")
    logger.debug(f"[safe_convert_item_fields] Raw ID: {raw_id} (type: {type(raw_id)})")

    if raw_id is None or raw_id == "":
        logger.error(
            f"[safe_convert_item_fields] Item missing required 'id' field: {item}"
        )
        raise ValueError(f"Item missing required 'id' field: {item}")

    try:
        item_id = int(raw_id)
        logger.debug(f"[safe_convert_item_fields] Converted item_id: {item_id}")
    except (ValueError, TypeError) as e:
        logger.error(
            f"[safe_convert_item_fields] Failed to convert raw_id '{raw_id}' to int: {e}"
        )
        raise ValueError(f"Invalid item ID '{raw_id}': {e}")

    # For MenuSifu: sale_item_id should always be the same as item_id
    sale_item_id = item_id

    # Safely convert price with validation (required field, default to 0)
    raw_price = item.get("price")
    logger.debug(
        f"[safe_convert_item_fields] Raw price: {raw_price} (type: {type(raw_price)})"
    )

    if raw_price is None or raw_price == "":
        price_val = Decimal("0")
        logger.debug(f"[safe_convert_item_fields] Using default price: {price_val}")
    else:
        try:
            price_val = Decimal(str(raw_price))
            logger.debug(f"[safe_convert_item_fields] Converted price: {price_val}")
        except (ValueError, TypeError, ArithmeticError) as e:
            # Default to 0 if conversion fails
            logger.error(
                f"[safe_convert_item_fields] Failed to convert price '{raw_price}': {e}"
            )
            price_val = Decimal("0")

    # Safely convert displayPrice (optional field) - keep raw value intact but ensure it's not None
    raw_display_price = item.get("displayPrice") or item.get("display_price")
    # Keep as-is but ensure it's not None for Pydantic validation
    display_price_val = (
        raw_display_price if raw_display_price is not None else price_val
    )

    # Safely convert categoryId with default (handle 0 as valid value)
    raw_category_id = item.get("categoryId")
    if raw_category_id is None:
        raw_category_id = item.get("category_id")

    if raw_category_id is None or raw_category_id == "":
        category_id_val = 0
    else:
        try:
            category_id_val = int(raw_category_id)
        except (ValueError, TypeError):
            category_id_val = 0

    # Safely convert quantity with default
    raw_quantity = item.get("quantity")
    if raw_quantity is None or raw_quantity == "":
        quantity_val = 1
    else:
        try:
            quantity_val = int(raw_quantity)
            # Ensure quantity is at least 1
            quantity_val = max(1, quantity_val)
        except (ValueError, TypeError):
            quantity_val = 1

    result = {
        "id": item_id,
        "saleItemId": sale_item_id,
        "price": price_val,
        "displayPrice": display_price_val,  # Raw value kept intact
        "categoryId": category_id_val,
        "quantity": quantity_val,
        "itemType": item.get("itemType") or item.get("item_type") or "SALE_ITEM",
        "name": item.get("name") or "",
    }

    logger.debug(f"[safe_convert_item_fields] Final result: {result}")
    logger.debug(
        f"[safe_convert_item_fields] Result types: {[(k, type(v)) for k, v in result.items()]}"
    )

    return result


def safe_convert_option_fields(option: Dict[str, Any]) -> Dict[str, Any]:
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
        try:
            option_price_val = Decimal(str(raw_option_price))
        except (ValueError, TypeError, ArithmeticError):
            # Default to None if conversion fails
            option_price_val = None

    # Safely convert option price (required field, default to 0)
    raw_price = option.get("price")
    if raw_price is None or raw_price == "":
        price_val = Decimal("0")
    else:
        try:
            price_val = Decimal(str(raw_price))
        except (ValueError, TypeError, ArithmeticError):
            # Default to 0 if conversion fails
            price_val = Decimal("0")

    # Safely convert option quantity with default
    raw_quantity = option.get("quantity")
    if raw_quantity is None or raw_quantity == "":
        quantity_val = 1
    else:
        try:
            quantity_val = int(raw_quantity)
            # Ensure quantity is at least 1
            quantity_val = max(1, quantity_val)
        except (ValueError, TypeError):
            quantity_val = 1

    return {
        "id": option.get("id"),  # Can be None for optional options
        "optionPrice": option_price_val,
        "price": price_val,
        "quantity": quantity_val,
        "name": option.get("name") or "",
        "checked": option.get("checked", True),
        "isOpenOption": option.get("isOpenOption", False),
    }


# =====================================================================================
# NEW FILTERING LOGIC - SIMPLE OUT-OF-STOCK ONLY FILTERING
# =====================================================================================


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that converts Decimal objects to float for serialization."""

    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)


def get_field_value(
    data: Dict[str, Any], camel_case_key: str, snake_case_key: str, default: Any = None
) -> Any:
    """
    Get field value handling both camelCase and snake_case naming conventions.

    Args:
        data: Dictionary to search in
        camel_case_key: camelCase field name (e.g., 'outOfStock')
        snake_case_key: snake_case field name (e.g., 'out_of_stock')
        default: Default value if neither field is found

    Returns:
        Field value from either naming convention, or default
    """
    return data.get(camel_case_key, data.get(snake_case_key, default))


def simple_filter_menu_items(menu_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Simple filtering that ONLY excludes out-of-stock items.

    This new filtering approach:
    - KEEPS hidden items (hiddenItem=true) - user specifically requested this
    - EXCLUDES only out-of-stock items (outOfStock=true)
    - PRESERVES all original metadata (hours, descriptions, categories, etc.)
    - HANDLES both camelCase (API) and snake_case (Pydantic) field names

    Args:
        menu_dict: Complete menu response dictionary

    Returns:
        Filtered menu dictionary with same structure, only sale_items filtered
    """
    # Create a deep copy to avoid modifying original
    filtered_menu = dict(menu_dict)

    if not filtered_menu.get("groups"):
        return filtered_menu

    # Track filtering statistics
    total_items = 0
    filtered_items = 0

    # Process each group (preserving all group data)
    filtered_groups = []
    for group in filtered_menu["groups"]:
        # Copy group data completely (preserving hours, descriptions, etc.)
        filtered_group = {**group}

        if not group.get("categories"):
            filtered_groups.append(filtered_group)
            continue

        # Process each category (preserving all category data)
        filtered_categories = []
        for category in group["categories"]:
            # Copy category data completely (preserving descriptions, options, etc.)
            filtered_category = {**category}

            # Handle both camelCase and snake_case for sale_items
            sale_items_key = "saleItems" if "saleItems" in category else "sale_items"
            sale_items = category.get(sale_items_key, [])

            if not sale_items:
                filtered_categories.append(filtered_category)
                continue

            # Filter sale items - ONLY exclude out-of-stock items
            filtered_sale_items = []
            for item in sale_items:
                total_items += 1

                # Check if item is out of stock (handle both naming conventions)
                out_of_stock = get_field_value(
                    item, "outOfStock", "out_of_stock", False
                )

                # ONLY filter out-of-stock items - keep everything else including hidden items
                if not out_of_stock:
                    filtered_sale_items.append(item)
                else:
                    filtered_items += 1

            # Update the filtered sale items
            filtered_category[sale_items_key] = filtered_sale_items
            filtered_categories.append(filtered_category)

        filtered_group["categories"] = filtered_categories
        filtered_groups.append(filtered_group)

    filtered_menu["groups"] = filtered_groups

    # Add filtering summary
    print("📊 Simple Filtering Results:")
    print(f"   Total items processed: {total_items}")
    print(f"   Items kept: {total_items - filtered_items}")
    print(f"   Out-of-stock items filtered: {filtered_items}")
    print("   ✅ Hidden items KEPT (as requested)")

    return filtered_menu


def save_filtered_menu_data(
    filtered_menu: Dict[str, Any], output_dir: str, generate_text_menu: bool = True
) -> Dict[str, str]:
    """
    Save filtered menu data in multiple formats.

    Args:
        filtered_menu: Filtered menu dictionary
        output_dir: Directory to save files in
        generate_text_menu: Whether to generate user-friendly text menu

    Returns:
        Dictionary with file paths that were created
    """
    import os

    created_files = {}

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Save filtered JSON menu
    clean_menu_path = os.path.join(output_dir, "clean_menu_response.json")
    with open(clean_menu_path, "w", encoding="utf-8") as f:
        json.dump(filtered_menu, f, indent=2, ensure_ascii=False, cls=DecimalEncoder)
    created_files["clean_menu_json"] = clean_menu_path
    print(f"💾 Saved filtered menu: {clean_menu_path}")

    # Generate text menu if requested
    if generate_text_menu:
        try:
            # Generate user-friendly bilingual menu directly from dict
            bilingual_content = generate_bilingual_menu_content(
                filtered_menu, user_friendly=True
            )

            bilingual_path = os.path.join(output_dir, "bilingual_menu.txt")
            with open(bilingual_path, "w", encoding="utf-8") as f:
                f.write(bilingual_content)
            created_files["bilingual_menu"] = bilingual_path
            print(f"📄 Saved bilingual menu: {bilingual_path}")

        except Exception as e:
            print(f"⚠️ Could not generate text menu: {e}")

    return created_files


# =====================================================================================
# ENHANCED EXISTING FUNCTIONS - FIELD NAME COMPATIBILITY
# =====================================================================================
