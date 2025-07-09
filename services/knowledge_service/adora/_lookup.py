"""
Menu data lookup and parsing operations for Adora integration.

This module provides functions to:
- Look up menu entities (categories, sizes, modifiers) by ID
- Parse formatted menu text back into structured data
- Extract specific information from text using regex patterns

Key responsibilities:
- ID-based lookups for menu hierarchy navigation
- Text parsing and data extraction utilities
- Converting formatted text back to structured dictionaries
"""

import re
from typing import Any, Dict, List, Optional


def find_by_id(
    items: List[Dict[str, Any]],
    id_field: str,
    target_id: str,
    name_field: str = "name",
    default: str = "Unknown",
) -> str:
    """Generic function to find an item by ID and return a specific field.

    Args:
        items: List of dictionaries to search
        id_field: The field name containing the ID to match
        target_id: The ID value to search for
        name_field: The field name to return (default: "name")
        default: Default value if not found

    Returns:
        str: The value of the name_field or default if not found
    """
    for item in items:
        if item.get(id_field) == target_id:
            return item.get(name_field, default)
    return default


def extract_text_between_markers(
    text: str, start_marker: str, end_marker: str
) -> Optional[str]:
    """Extract text between two markers using regex.

    Args:
        text: The text to search in
        start_marker: The starting marker pattern
        end_marker: The ending marker pattern

    Returns:
        str: The extracted text or None if not found
    """
    pattern = f"{re.escape(start_marker)}(.*?){re.escape(end_marker)}"
    match = re.search(pattern, text, re.DOTALL)
    return match.group(1).strip() if match else None


def get_category_name(categories: List[Dict[str, Any]], category_id: str) -> str:
    """Get category name by ID.

    Args:
        categories: List of category dictionaries
        category_id: The category ID to look up

    Returns:
        str: The category name or "Unknown" if not found
    """
    return find_by_id(categories, "category_id", category_id, "name", "Unknown")


def get_size_description(sizes: List[Dict[str, Any]], size_id: str) -> str:
    """Get size description by ID.

    Args:
        sizes: List of size dictionaries
        size_id: The size ID to look up

    Returns:
        str: The size description or a default description
    """
    for s in sizes:
        if s.get("size_id") == size_id:
            desc = s.get("description", "")
            name = s.get("name", "")
            if desc != name and name and name != "None":
                return f"{desc}, {name}"
            return desc or f"Size {size_id}"
    return f"Size {size_id}"


def get_modifier_group_name(
    modifier_groups: List[Dict[str, Any]], group_id: str
) -> str:
    """Get modifier group name by ID.

    Args:
        modifier_groups: List of modifier group dictionaries
        group_id: The modifier group ID to look up

    Returns:
        str: The modifier group name or a default name
    """
    return find_by_id(
        modifier_groups, "modifier_group_id", group_id, "name", f"Group {group_id}"
    )


def parse_item_data(item_text: str) -> Optional[Dict[str, Any]]:
    """Parse item text to extract structured data.

    Args:
        item_text: The formatted item text string

    Returns:
        dict: Parsed item data with name, id, category, description, prices, and included items
        None: If parsing fails
    """
    # Extract item name and ID from first line
    first_line = item_text.split("\n")[0]
    name_match = re.match(r"# (.+) \(item_id: (\d+)\)", first_line)
    if not name_match:
        return None

    item_name = name_match.group(1)
    item_id = name_match.group(2)

    # Extract category using general utility
    category = (
        extract_text_between_markers(item_text, "**Category:** ", "\n") or "Other"
    )

    # Extract description using general utility
    description = (
        extract_text_between_markers(item_text, "**Description:** ", "\n") or ""
    )

    # Extract prices
    prices = []
    price_section = re.search(r"## Prices\n(.*?)(?=\n##|\n$)", item_text, re.DOTALL)
    if price_section:
        price_lines = price_section.group(1).strip().split("\n")
        for line in price_lines:
            if line.strip().startswith("- "):
                price_match = re.match(
                    r"- (.+?) \(size_id: \d+\): \$(.+)", line.strip()
                )
                if price_match:
                    size_name = price_match.group(1)
                    price = price_match.group(2)
                    prices.append(f"${price} ({size_name})")

    # Extract included modifiers
    included_items = []
    modifier_section = re.search(r"## Modifiers\n(.*?)$", item_text, re.DOTALL)
    if modifier_section:
        modifier_content = modifier_section.group(1)
        included_sections = re.findall(
            r"#### Included in the price\n((?:- .+\n?)*)", modifier_content
        )
        for section in included_sections:
            lines = section.strip().split("\n")
            for line in lines:
                if line.strip().startswith("- "):
                    modifier_match = re.match(
                        r"- (.+?) \(modifier_id: \d+\)", line.strip()
                    )
                    if modifier_match:
                        included_items.append(modifier_match.group(1))

    return {
        "name": item_name,
        "id": item_id,
        "category": category,
        "description": description,
        "prices": prices,
        "included": included_items,
    }
