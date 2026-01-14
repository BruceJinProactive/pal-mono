"""
Menu data utilities for Adora integration.

This module provides utility functions to:
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


def get_modifier_group_constraints(
    modifier_groups: List[Dict[str, Any]], group_id: str
) -> Dict[str, Optional[int]]:
    """Get modifier group constraints by ID.

    Args:
        modifier_groups: List of modifier group dictionaries
        group_id: The modifier group ID to look up

    Returns:
        dict: Dictionary with 'min_required_modifier' and 'max_allowed_modifier' keys
    """
    for group in modifier_groups:
        if group.get("modifier_group_id") == group_id:
            return {
                "min_required_modifier": group.get("min_required_modifier"),
                "max_allowed_modifier": group.get("max_allowed_modifier"),
            }
    return {"min_required_modifier": None, "max_allowed_modifier": None}


def _parse_modifier_lines(lines_text: str) -> List[Dict[str, str]]:
    """Parse modifier lines and extract name and pricing information."""
    modifiers = []
    lines = lines_text.strip().split("\n")
    for line in lines:
        if line.strip().startswith("- "):
            # Handle formats: "- Bacon", "- Bacon (modifier_id: 123)", or "- Bacon (modifier_id: 123) (price not available)"

            # Try to match with pricing info first
            pricing_match = re.match(
                r"- (.+?)(?:\s*\(modifier_id: \d+\))?\s*(\(price not available\)|\(\+\$[\d.]+.*?\))",
                line.strip(),
            )

            if pricing_match:
                modifier_name = pricing_match.group(1).strip()
                pricing_text = pricing_match.group(2).strip()
                modifiers.append({"name": modifier_name, "pricing": pricing_text})
            else:
                # No pricing info - just name with optional modifier_id
                name_match = re.match(
                    r"- (.+?)(?:\s*\(modifier_id: \d+\))?$", line.strip()
                )
                if name_match:
                    modifier_name = name_match.group(1).strip()
                    modifiers.append({"name": modifier_name, "pricing": ""})

    return modifiers


def parse_item_data(item_text: str) -> Optional[Dict[str, Any]]:
    """Parse item text to extract structured data.

    Args:
        item_text: The formatted item text string

    Returns:
        dict: Parsed item data with name, id, category, description, prices, included items, and modifier groups
        None: If parsing fails
    """
    # Extract item name and ID from first line
    first_line = item_text.split("\n")[0]
    name_match = re.match(r"# (.+) \(item_id: (\d+)\)", first_line)
    if not name_match:
        # Try parsing without item_id (for no_ids format)
        name_match = re.match(r"# (.+)$", first_line)
        if not name_match:
            return None
        item_name = name_match.group(1)
        item_id = None
    else:
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

    # Extract allow_halving flag (handles both with and without explanation text)
    if "**allow_halving:** true" in item_text:
        allow_halving = True
    elif "**allow_halving:** false" in item_text:
        allow_halving = False
    else:
        allow_halving = False  # Default to false if not found

    # Extract prices
    prices = []
    price_section = re.search(r"## Prices\n(.*?)(?=\n##|\n$)", item_text, re.DOTALL)
    if price_section:
        price_lines = price_section.group(1).strip().split("\n")
        for line in price_lines:
            if line.strip().startswith("- "):
                # Handle both formats: with and without size_id
                price_match = re.match(
                    r"- (.+?) \(size_id: \d+\): \$(.+)", line.strip()
                ) or re.match(r"- (.+?): \$(.+)", line.strip())
                if price_match:
                    size_name = price_match.group(1)
                    price = price_match.group(2)
                    prices.append(f"${price} ({size_name})")

    # Extract included modifiers and modifier groups
    included_items = []
    modifier_groups = []
    modifier_section = re.search(r"## Modifiers\n(.*?)$", item_text, re.DOTALL)
    if modifier_section:
        modifier_content = modifier_section.group(1)

        # Parse modifier groups - look for ### followed by space or end, not ####
        group_sections = re.findall(
            r"### (.+?)\n(.*?)(?=\n###(?:\s|\Z)|\Z)", modifier_content, re.DOTALL
        )
        for group_name, group_content in group_sections:
            # Parse group name and constraints
            # Group name might have constraint info like "Extra Toppings (Select 0-3)"
            clean_group_name = group_name.strip()
            constraints = {}

            # Extract allow_halving information from group name if present
            if "[allow_halving: true]" in clean_group_name:
                group_allow_halving = True
                clean_group_name = clean_group_name.replace(
                    "[allow_halving: true]", ""
                ).strip()
            elif "[allow_halving: false]" in clean_group_name:
                group_allow_halving = False
                clean_group_name = clean_group_name.replace(
                    "[allow_halving: false]", ""
                ).strip()
            else:
                group_allow_halving = False  # Default to false if not found

            # Extract constraint information from group name if present
            constraint_match = re.search(r"(.+?)\s*\((Select.*?)\)", clean_group_name)
            if constraint_match:
                clean_group_name = constraint_match.group(1).strip()
                constraint_text = constraint_match.group(2)

                # Parse different constraint patterns
                if "exactly" in constraint_text:
                    # "Select exactly 1"
                    exact_match = re.search(r"exactly (\d+)", constraint_text)
                    if exact_match:
                        num = int(exact_match.group(1))
                        constraints = {"min_required": num, "max_allowed": num}
                elif "at least" in constraint_text:
                    # "Select at least 2"
                    min_match = re.search(r"at least (\d+)", constraint_text)
                    if min_match:
                        constraints = {
                            "min_required": int(min_match.group(1)),
                            "max_allowed": None,
                        }
                elif "up to" in constraint_text:
                    # "Select up to 3"
                    max_match = re.search(r"up to (\d+)", constraint_text)
                    if max_match:
                        constraints = {
                            "min_required": None,
                            "max_allowed": int(max_match.group(1)),
                        }
                elif re.match(r"Select \d+-\d+", constraint_text):
                    # "Select 1-3"
                    range_match = re.search(r"Select (\d+)-(\d+)", constraint_text)
                    if range_match:
                        constraints = {
                            "min_required": int(range_match.group(1)),
                            "max_allowed": int(range_match.group(2)),
                        }

            group_data = {
                "name": clean_group_name,
                "included": [],
                "optional": [],
                "constraints": constraints,
                "allow_halving": group_allow_halving,
            }

            # Extract included modifiers
            included_sections = re.findall(
                r"#### Included.*?\n((?:- .+\n?)*)", group_content
            )
            for section in included_sections:
                parsed_modifiers = _parse_modifier_lines(section)
                for mod in parsed_modifiers:
                    group_data["included"].append(mod)
                    included_items.append(mod["name"])

            # Extract optional modifiers
            optional_sections = re.findall(
                r"#### Optional.*?\n((?:- .+\n?)*)", group_content
            )
            for section in optional_sections:
                parsed_modifiers = _parse_modifier_lines(section)
                group_data["optional"].extend(parsed_modifiers)

            modifier_groups.append(group_data)

    return {
        "name": item_name,
        "id": item_id,
        "category": category,
        "description": description,
        "prices": prices,
        "included": included_items,
        "modifier_groups": modifier_groups,
        "allow_halving": allow_halving,
    }
