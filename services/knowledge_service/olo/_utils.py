"""
OLO menu data utilities and parsing functions.

This module provides utility functions for processing OLO menu data:
- Parse complex OLO menu JSON structures
- Handle modifier groups and nested modifiers
- Format pricing information
- Detect and handle circular references in modifier structures
- Generate clean, readable menu text formats in Toast-style

Key responsibilities:
- JSON parsing and data extraction from OLO API responses
- Modifier hierarchy processing with cycle detection
- Text sanitization for file system compatibility
- Menu item organization
- Toast-style hierarchical formatting
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from utils.log import logger


def _sanitize_filename(filename: str) -> str:
    """Sanitize filename by replacing problematic characters with safe alternatives.

    Args:
        filename: Raw filename string

    Returns:
        Sanitized filename safe for filesystem use
    """
    # Replace problematic characters with readable alternatives
    sanitized = filename
    sanitized = re.sub(
        r"/", " or ", sanitized
    )  # Replace slash with "or" for better readability
    sanitized = re.sub(r"\\", " and ", sanitized)  # Replace backslash with "and"
    sanitized = re.sub(
        r'[<"|?*]', "_", sanitized
    )  # Replace other invalid chars with underscore
    sanitized = re.sub(r"[(){}\[\]]", "", sanitized)  # Remove brackets/parentheses
    sanitized = re.sub(r"\s+", " ", sanitized)  # Collapse multiple spaces
    sanitized = sanitized.strip()  # Remove leading/trailing whitespace

    # Ensure filename isn't too long (max 255 chars for most filesystems)
    if len(sanitized) > 200:  # Leave some room for extension
        sanitized = sanitized[:200].strip()

    return sanitized


def _format_option_with_price(option: Dict[str, Any]) -> str:
    """Format option with price in Toast style.

    Args:
        option: Option dict with 'name' and 'cost' keys

    Returns:
        Formatted string like "Option Name (+$1.99)"
    """
    name = option.get("name", "")
    cost = option.get("cost", 0)

    if cost is not None and cost > 0:
        return f"{name} (+${cost:.2f})"
    else:
        return f"{name} (+$0.0)"


def _build_constraint_text(modifier_group: Dict[str, Any]) -> str:
    """Build constraint description for modifier group.

    Args:
        modifier_group: Modifier group dict with mandatory/minselects/maxselects

    Returns:
        Formatted constraint string like "(Required, Select exactly 2)"
    """
    mandatory = modifier_group.get("mandatory", False)
    minselects = modifier_group.get("minselects")
    maxselects = modifier_group.get("maxselects")

    constraint_parts = []

    # Required or Optional
    if mandatory:
        constraint_parts.append("Required")
    else:
        constraint_parts.append("Optional")

    # Selection constraints
    if minselects is not None and maxselects is not None:
        if minselects == maxselects:
            constraint_parts.append(f"Select exactly {minselects}")
        else:
            constraint_parts.append(f"Select {minselects}-{maxselects} options")
    elif maxselects is not None:
        constraint_parts.append(f"Select up to {maxselects} options")
    elif minselects is not None and minselects > 0:
        constraint_parts.append(f"Select {minselects}+ options")
    else:
        constraint_parts.append("Select any number")

    return "(" + ", ".join(constraint_parts) + ")"


def _format_nested_modifier_options(
    option: Dict[str, Any],
    indent_level: int,
    visited: Optional[set[object]] = None,
) -> List[str]:
    """Recursively format nested modifier options with cycle detection.

    Args:
        option: Modifier option that may have nested modifiers
        indent_level: Current indentation level (number of tabs)
        visited: Set of visited option IDs for cycle detection

    Returns:
        List of formatted strings with proper indentation
    """
    if visited is None:
        visited = set()

    nested_lines = []
    option_id = option.get("id")
    unique_key = option_id if option_id is not None else id(option)

    # Prevent infinite recursion by tracking visited options
    if unique_key in visited:
        logger.debug(
            f"[olo._utils._format_nested_modifier_options] Circular reference detected for option ID {option_id} (key: {unique_key})"
        )
        return []

    visited.add(unique_key)

    # Check if this option has nested modifiers
    nested_modifiers = option.get("modifiers", [])
    if not nested_modifiers:
        return []

    # Process each nested modifier group
    for modifier_group in nested_modifiers:
        group_name = modifier_group.get("description", "Modifiers")
        constraint_text = _build_constraint_text(modifier_group)

        # Get options for this group
        group_options = modifier_group.get("options", [])

        # Separate options with and without further nesting
        simple_options = []
        complex_options = []

        for opt in group_options:
            if opt.get("modifiers"):
                complex_options.append(opt)
            else:
                simple_options.append(opt)

        # Format the group line
        tabs = "\t" * indent_level

        if simple_options and not complex_options:
            # All options are simple - put them on one line
            option_strs = [_format_option_with_price(opt) for opt in simple_options]
            nested_lines.append(
                f"{tabs}{group_name} {constraint_text}: {', '.join(option_strs)}"
            )
        elif simple_options and complex_options:
            # Mix of simple and complex - simple ones on main line, complex ones nested
            option_strs = [_format_option_with_price(opt) for opt in simple_options]
            nested_lines.append(
                f"{tabs}{group_name} {constraint_text}: {', '.join(option_strs)}"
            )
            # Add complex options on separate lines with further nesting
            for complex_opt in complex_options:
                nested_lines.append(f"{tabs}\t{_format_option_with_price(complex_opt)}")
                # Recursively format deeper nesting
                deeper_lines = _format_nested_modifier_options(
                    complex_opt, indent_level + 2, visited.copy()
                )
                nested_lines.extend(deeper_lines)
        else:
            # Only complex options - show group header
            nested_lines.append(f"{tabs}{group_name} {constraint_text}:")
            for complex_opt in complex_options:
                nested_lines.append(f"{tabs}\t{_format_option_with_price(complex_opt)}")
                # Recursively format deeper nesting
                deeper_lines = _format_nested_modifier_options(
                    complex_opt, indent_level + 2, visited.copy()
                )
                nested_lines.extend(deeper_lines)

    return nested_lines


def _format_modifier_group_system_prompt(
    modifier_group: Dict[str, Any],
    indent_level: int,
) -> List[str]:
    """Format modifier group in Toast-style hierarchical format.

    Args:
        modifier_group: Modifier group dict with options
        indent_level: Current indentation level (tabs)

    Returns:
        List of formatted modifier strings
    """
    modifier_lines = []

    group_name = modifier_group.get("description", "Modifiers")
    constraint_text = _build_constraint_text(modifier_group)
    options = modifier_group.get("options", [])

    if not options:
        tabs = "\t" * indent_level
        modifier_lines.append(f"{tabs}{group_name} {constraint_text}")
        return modifier_lines

    # Separate options with and without nested modifiers
    simple_options = []
    complex_options = []

    for option in options:
        if option.get("modifiers"):
            complex_options.append(option)
        else:
            simple_options.append(option)

    tabs = "\t" * indent_level

    # Format based on option types
    if simple_options and not complex_options:
        # All simple - one line
        option_strs = [_format_option_with_price(opt) for opt in simple_options]
        modifier_lines.append(
            f"{tabs}{group_name} {constraint_text}: {', '.join(option_strs)}"
        )
    elif simple_options and complex_options:
        # Mixed - simple on main line, complex nested
        option_strs = [_format_option_with_price(opt) for opt in simple_options]
        modifier_lines.append(
            f"{tabs}{group_name} {constraint_text}: {', '.join(option_strs)}"
        )
        # Add complex options with nesting
        for complex_opt in complex_options:
            modifier_lines.append(f"{tabs}\t{_format_option_with_price(complex_opt)}")
            nested_lines = _format_nested_modifier_options(
                complex_opt, indent_level + 2, None
            )
            modifier_lines.extend(nested_lines)
    else:
        # Only complex options
        modifier_lines.append(f"{tabs}{group_name} {constraint_text}:")
        for complex_opt in complex_options:
            modifier_lines.append(f"{tabs}\t{_format_option_with_price(complex_opt)}")
            nested_lines = _format_nested_modifier_options(
                complex_opt, indent_level + 2, None
            )
            modifier_lines.extend(nested_lines)

    return modifier_lines


def _build_system_prompt_item(product: Dict[str, Any], category: str) -> str:
    """Build Toast-style system prompt format for a single item.

    Args:
        product: Product dict from OLO API
        category: Category name

    Returns:
        Formatted item string with hierarchical modifiers
    """
    name = product.get("name", "")
    cost = product.get("cost", 0)
    description = product.get("description", "")
    modifiers = product.get("modifiers", {})

    # Line 1: Name and price
    if cost and cost > 0:
        item_lines = [f"{name} - ${cost:.2f}"]
    else:
        item_lines = [f"{name} - Available"]

    # Line 2: Description (if short enough)
    if description and len(description) < 100:
        item_lines.append(f"  {description}")

    # Format modifiers in Toast style
    modifier_groups = modifiers.get("optiongroups", [])
    if modifier_groups:
        all_modifier_lines = []
        for group in modifier_groups:
            group_lines = _format_modifier_group_system_prompt(group, indent_level=1)
            all_modifier_lines.extend(group_lines)

        if all_modifier_lines:
            # Add "Customizations:" prefix to first modifier line
            if all_modifier_lines:
                first_line = all_modifier_lines[0]
                # Remove leading tab and add "Customizations: " prefix
                if first_line.startswith("\t"):
                    first_line = "\tCustomizations: " + first_line[1:]
                    all_modifier_lines[0] = first_line

            item_lines.extend(all_modifier_lines)

    return "\n".join(item_lines)


def _format_modifier_info_detailed(product: Dict[str, Any]) -> List[str]:
    """Format detailed modifier information for individual item files.

    This maintains the current OLO format with all IDs preserved.

    Args:
        product: Product dict with modifiers

    Returns:
        List of formatted lines with all IDs preserved
    """
    modifier_lines = []
    modifiers = product.get("modifiers", {})
    modifier_groups = modifiers.get("optiongroups", [])

    if not modifier_groups:
        return []

    modifier_lines.append("Modifiers:")

    for group in modifier_groups:
        group_id = group.get("id")
        group_name = group.get("description", "")
        mandatory = group.get("mandatory", False)
        minselects = group.get("minselects")
        maxselects = group.get("maxselects")

        # Format group header
        if minselects is not None and maxselects is not None:
            modifier_lines.append(
                f"\tModifiers for {product['name']}: {group_name} (ChoiceID: {group_id}, Minimum quantity: {minselects}, Maximum quantity: {maxselects})"
            )
        else:
            modifier_lines.append(
                f"\tModifiers for {product['name']}: {group_name} (ChoiceID: {group_id}, Mandatory: {mandatory})"
            )

        # Format options recursively
        options = group.get("options", [])
        modifier_lines.extend(_format_options_detailed(options, indent=2))

    return modifier_lines


def _format_options_detailed(
    options: List[Dict[str, Any]],
    indent: int = 2,
    visited: Optional[set[object]] = None,
) -> List[str]:
    """Recursively format options in detailed format with IDs.

    Args:
        options: List of option dicts
        indent: Current indentation level (tabs)
        visited: Set of visited option unique keys for cycle detection

    Returns:
        List of formatted option lines
    """
    # Initialize visited set
    if visited is None:
        visited = set()

    lines = []
    tabs = "\t" * indent

    for option in options:
        option_id = option.get("id")
        option_name = option.get("name", "")
        option_cost = option.get("cost", 0)

        # Get unique key for cycle detection
        unique_key = option_id if option_id is not None else id(option)

        # Check for cycles
        if unique_key in visited:
            logger.debug(
                f"[olo._utils._format_options_detailed] Circular reference detected for option ID {option_id} (key: {unique_key})"
            )
            continue  # Skip this option to avoid infinite recursion

        # Add to visited set
        visited.add(unique_key)

        lines.append(
            f"{tabs}- {option_name} (ChoiceID: {option_id}, Cost: ${option_cost})"
        )

        # Handle nested modifiers
        nested_modifiers = option.get("modifiers", [])
        if nested_modifiers:
            lines.append(f"{tabs}\tModifiers for {option_name}:")

            for nested_group in nested_modifiers:
                group_id = nested_group.get("id")
                group_name = nested_group.get("description", "")
                mandatory = nested_group.get("mandatory", False)
                minselects = nested_group.get("minselects")
                maxselects = nested_group.get("maxselects")

                if minselects is not None and maxselects is not None:
                    lines.append(
                        f"{tabs}\t\t- {group_name} (ChoiceID: {group_id}, Minimum quantity: {minselects}, Maximum quantity: {maxselects})"
                    )
                else:
                    lines.append(
                        f"{tabs}\t\t- {group_name} (ChoiceID: {group_id}, Mandatory: {mandatory})"
                    )

                lines.append(f"{tabs}\t\tModifiers:")

                # Recursively format nested options - pass visited set
                nested_options = nested_group.get("options", [])
                lines.extend(
                    _format_options_detailed(nested_options, indent + 3, visited.copy())
                )

    return lines


def _build_individual_item(product: Dict[str, Any], category: str) -> Dict[str, str]:
    """Build detailed item format with all IDs preserved.

    Args:
        product: Product dict from OLO
        category: Category name

    Returns:
        Dict with single key-value: {item_name: detailed_content}
    """
    name = product.get("name", "")
    product_id = product.get("id", "")
    cost = product.get("cost", 0)
    description = product.get("description", "")

    # Build item content
    item_lines = [f"Name: {name} (ProductID: {product_id}, Cost: ${cost})"]

    if description:
        item_lines.append(f"Description: {description}")

    # Add detailed modifiers
    modifier_lines = _format_modifier_info_detailed(product)
    item_lines.extend(modifier_lines)

    item_content = "\n".join(item_lines)

    # Return as dict with category prefix
    item_name = f"{category}: {name}" if category else name
    return {item_name: item_content}


def parse_menu(
    json_data: Dict[str, Any],
) -> Tuple[List[Dict[str, str]], str]:
    """
    Parse OLO menu JSON and generate both formats.

    Args:
        json_data: Complete menu data with categories and products

    Returns:
        Tuple of (individual_items_list, system_prompt_menu_string)
    """
    logger.debug("[olo._utils.parse_menu] Starting menu parsing...")

    individual_items: List[Dict[str, str]] = []
    system_prompt_items: List[str] = []

    # Process regular categories
    categories = json_data.get("categories", {})
    for category_name, products in categories.items():
        logger.debug(
            f"[olo._utils.parse_menu] Processing category: {category_name} ({len(products)} items)"
        )

        for product in products:
            # Build individual item (detailed with IDs)
            individual_item = _build_individual_item(product, category_name)
            individual_items.append(individual_item)

            # Build system prompt item (clean, hierarchical)
            system_prompt_item = _build_system_prompt_item(product, category_name)
            system_prompt_items.append(system_prompt_item)

    # Process single use categories
    single_use_categories = json_data.get("single_use_categories", {})
    for category_name, products in single_use_categories.items():
        logger.debug(
            f"[olo._utils.parse_menu] Processing single-use category: {category_name} ({len(products)} items)"
        )

        for product in products:
            # Build individual item
            individual_item = _build_individual_item(product, category_name)
            individual_items.append(individual_item)

            # Build system prompt item
            system_prompt_item = _build_system_prompt_item(product, category_name)
            system_prompt_items.append(system_prompt_item)

    # Join system prompt items with separator
    separator = "\n\n" + "#" * 50 + "\n\n"
    system_prompt_menu = separator.join(system_prompt_items)

    logger.debug(
        f"[olo._utils.parse_menu] Parsing complete. Generated {len(individual_items)} items"
    )

    return individual_items, system_prompt_menu
