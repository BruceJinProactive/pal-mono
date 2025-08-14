"""
Utility functions for MenuSifu tool operations
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Union

from .classes import (
    DetailPrice,
    LocalizedName,
    MenuResponse,
    Option,
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
        getattr(item, "base_price", None) if hasattr(item, "base_price") else None
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
    """Extract boolean properties as tags (e.g., Spicy, Vegetarian)."""
    tags: List[str] = []

    # Handle both object and dict access patterns
    item_properties = (
        getattr(item, "properties", None) if hasattr(item, "properties") else None
    )

    if item_properties:
        for prop in item_properties or []:
            if isinstance(prop, Property) and (
                prop.value is True or prop.value is None
            ):
                name = prop.display_name or prop.name
                if name:
                    tags.append(str(name))
            elif isinstance(prop, dict) and (
                prop.get("value") is True or prop.get("value") is None
            ):
                name = prop.get("displayName") or prop.get("name")
                if name:
                    tags.append(str(name))
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


def _extract_options(item, locale: str) -> List[str]:
    """Flatten options to simple human-friendly strings."""
    option_lines: List[str] = []

    # Handle both object and dict access patterns
    item_options = getattr(item, "options", None) if hasattr(item, "options") else None

    if not item_options:
        return option_lines

    for opt in item_options or []:
        if isinstance(opt, Option):
            opt_name = _localized_to_text(opt.name, locale)
            subparts = (
                _render_subparts(opt.sub_options or [], locale)
                if opt.sub_options
                else []
            )
            price_text = _format_price(opt.price)
            _append_option_line(option_lines, opt_name, price_text, subparts)
        elif isinstance(opt, dict):
            opt_name = _localized_to_text(opt.get("name", {}), locale)
            subparts = _render_subparts(opt.get("subOptions", []), locale)
            price_text = _format_price(opt.get("price"))
            _append_option_line(option_lines, opt_name, price_text, subparts)
    return option_lines


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


def generate_bilingual_menu_content(
    menu: Union[MenuResponse, Dict[str, Any]],
) -> str:
    """Generate a single unified menu with both English and Chinese content."""
    lines = []

    # Handle both MenuResponse objects and raw dictionaries
    if isinstance(menu, dict):
        menu_name = menu.get("name", {})
        menu_groups = menu.get("groups", [])
    else:
        menu_name = menu.name
        menu_groups = menu.groups

    # Menu title
    menu_name_en = (
        menu_name.get("en", "Menu") if isinstance(menu_name, dict) else "Menu"
    )
    menu_name_zh = menu_name.get("zh-cn", "") if isinstance(menu_name, dict) else ""

    if menu_name_zh:
        lines.append(f"{menu_name_en} / {menu_name_zh}")
    else:
        lines.append(menu_name_en)
    lines.append("=" * len(lines[-1]))
    lines.append("")

    # Process groups and categories
    for group in menu_groups:
        # Handle both object and dict access
        if isinstance(group, dict):
            group_name = group.get("name", {})
            group_categories = group.get("categories", [])
        else:
            group_name = group.name
            group_categories = group.categories

        # Group name
        group_name_en = group_name.get("en", "") if isinstance(group_name, dict) else ""
        group_name_zh = (
            group_name.get("zh-cn", "") if isinstance(group_name, dict) else ""
        )

        if group_name_en:
            if group_name_zh:
                group_title = f"{group_name_en} / {group_name_zh}"
            else:
                group_title = group_name_en

            lines.append(group_title)
            lines.append("-" * len(group_title))
            lines.append("")

        # Process categories
        for category in group_categories:
            # Handle both object and dict access
            if isinstance(category, dict):
                category_name = category.get("name", {})
                category_description = category.get("description", "")
                category_items = category.get("saleItems", [])
            else:
                category_name = category.name
                category_description = category.description or ""
                category_items = category.sale_items

            # Category name
            cat_name_en = (
                category_name.get("en", "") if isinstance(category_name, dict) else ""
            )
            cat_name_zh = (
                category_name.get("zh-cn", "")
                if isinstance(category_name, dict)
                else ""
            )

            if cat_name_en:
                if cat_name_zh:
                    cat_title = f"## {cat_name_en} / {cat_name_zh}"
                else:
                    cat_title = f"## {cat_name_en}"
                lines.append(cat_title)

                # Category description if available
                if category_description:
                    lines.append(category_description)
                lines.append("")

            # Process items
            for item in category_items:
                # Create a SaleItem object for compatibility with _format_prices
                if isinstance(item, dict):
                    # Use SaleItem.model_validate to create proper Pydantic object
                    try:
                        item_obj = SaleItem.model_validate(item)
                        item_name = item.get("name", {})
                    except Exception:
                        # Fallback: create SaleItem with minimal required fields using aliases
                        item_data = {
                            "id": item.get("id", 0),
                            "name": item.get("name", {}),
                            "itemType": item.get("itemType", "SALE_ITEM"),
                            "price": item.get("price"),
                            "basePrice": item.get("basePrice"),
                            "detailPrice": item.get("detailPrice"),
                            "properties": item.get("properties", []),
                            "options": item.get("options", []),
                        }
                        # Remove None values to avoid validation issues
                        item_data = {
                            k: v for k, v in item_data.items() if v is not None
                        }
                        item_obj = SaleItem.model_validate(item_data)
                        item_name = item.get("name", {})
                else:
                    item_obj = item
                    item_name = item.name

                # Get prices (filtered for zero prices)
                prices = _format_prices(item_obj)

                # Skip items with no valid prices (zero prices filtered out)
                if not prices:
                    continue

                # Item names
                item_name_en = (
                    item_name.get("en", "") if isinstance(item_name, dict) else ""
                )
                item_name_zh = (
                    item_name.get("zh-cn", "") if isinstance(item_name, dict) else ""
                )

                if item_name_en:
                    if item_name_zh:
                        item_title = f"{item_name_en} / {item_name_zh}"
                    else:
                        item_title = item_name_en

                    # Format with prices
                    price_text = ", ".join(prices)
                    lines.append(f"- {item_title} — {price_text}")

                    # Add properties if any
                    properties = _extract_properties(item_obj)
                    if properties:
                        lines.append(f"  Properties: {', '.join(properties)}")

                    # Add options if any (bilingual)
                    options = _extract_bilingual_options(item)
                    if options:
                        lines.append(f"  Options: {', '.join(options)}")

            lines.append("")  # Space after each category

    return "\n".join(lines).strip()


def generate_bilingual_menu_file(
    menu: Union[MenuResponse, Dict[str, Any]],
    output_dir: str,
    filename: str = "bilingual_menu.txt",
) -> str:
    """Generate and save a bilingual menu file with both English and Chinese content."""
    os.makedirs(output_dir, exist_ok=True)

    bilingual_content = generate_bilingual_menu_content(menu)

    file_path = os.path.abspath(os.path.join(output_dir, filename))

    with open(file_path, "w", encoding="utf-8") as f:
        f.write("BILINGUAL MENU (ENGLISH & CHINESE)\n")
        f.write("=" * 80 + "\n\n")
        f.write(bilingual_content)

    return file_path
