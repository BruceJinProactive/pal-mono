"""
Toast menu data utilities and parsing functions.

This module provides utility functions for processing Toast menu data:
- Parse complex Toast menu JSON structures
- Handle modifier groups and nested modifiers
- Format pricing information with different strategies
- Detect and handle infinite loops in modifier structures
- Generate clean, readable menu text formats

Key responsibilities:
- JSON parsing and data extraction from Toast API responses
- Modifier hierarchy processing with cycle detection
- Pricing strategy interpretation and formatting
- Text sanitization for file system compatibility
- Menu item organization and context building

Migrated from tools/toast_tool/test/_utils.py to provide centralized
Toast menu processing capabilities for the knowledge service.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from utils.log import logger


def _sanitize_filename(filename: str) -> str:
    """Sanitize filename by replacing problematic characters with safe alternatives."""
    # Replace problematic characters with readable alternatives
    sanitized = filename
    sanitized = re.sub(
        r"/", " or ", sanitized
    )  # Replace slash with "or" for better readability
    sanitized = re.sub(r"\\", " and ", sanitized)  # Replace backslash with "and"
    sanitized = re.sub(
        r'[<"|?*]', "_", sanitized
    )  # Replace other invalid chars with underscore (keeping > for arrows and : for separation)
    # Keep arrows (->) as they are readable and safe for filenames
    sanitized = re.sub(r"[(){}[\]]", "", sanitized)  # Remove brackets/parentheses
    sanitized = re.sub(r"\s+", " ", sanitized)  # Collapse multiple spaces
    sanitized = sanitized.strip()  # Remove leading/trailing whitespace

    # Ensure filename isn't too long (max 255 chars for most filesystems)
    if len(sanitized) > 200:  # Leave some room for extension
        sanitized = sanitized[:200].strip()

    return sanitized


def _build_hierarchy_context(menu_name: str, parent_group: str, group_name: str) -> str:
    """Build hierarchical context string from menu components."""
    components = [comp for comp in [menu_name, parent_group, group_name] if comp]
    return " -> ".join(components)


def _has_infinite_loop(
    item: Dict[str, Any],
    modifier_groups: Dict[str, Any],
    modifier_options: Dict[str, Any],
    visited_items: Optional[set] = None,
) -> bool:
    """
    Check if a menu item has infinite loops in its modifier structure.

    According to Toast guidelines: "If your integration encounters a modifier option
    whose item reference is the same as the modifier option's parent menu item,
    your integration should stop looping through the menu JSON and not display the modifier option."
    """
    if visited_items is None:
        visited_items = set()

    item_guid = item.get("guid")
    if item_guid in visited_items:
        return True

    visited_items.add(item_guid)

    # Check all modifier groups for this item
    for modifier_ref in item.get("modifierGroupReferences", []):
        mod_group = modifier_groups.get(str(modifier_ref))
        if not mod_group:
            continue

        # Check all options in this modifier group
        for option_ref in mod_group.get("modifierOptionReferences", []):
            option = modifier_options.get(str(option_ref))
            if not option:
                continue

            # Check if this option has nested modifiers that could loop back
            for nested_modifier_ref in option.get("modifierGroupReferences", []):
                nested_mod_group = modifier_groups.get(str(nested_modifier_ref))
                if not nested_mod_group:
                    continue

                # Check if any option in the nested group references back to our original item
                for nested_option_ref in nested_mod_group.get(
                    "modifierOptionReferences", []
                ):
                    nested_option = modifier_options.get(str(nested_option_ref))
                    if nested_option and nested_option.get("guid") == item_guid:
                        logger.debug(
                            "WARNING: Infinite loop detected for item '%s' (GUID: %s)",
                            item.get("name"),
                            item_guid,
                        )
                        return True

                    # Recursively check deeper nesting
                    if (
                        nested_option
                        and item_guid
                        and _has_infinite_loop_in_option(
                            nested_option,
                            item_guid,
                            modifier_groups,
                            modifier_options,
                            visited_items.copy(),
                        )
                    ):
                        return True

    return False


def _has_infinite_loop_in_option(
    option: Dict[str, Any],
    target_item_guid: str,
    modifier_groups: Dict[str, Any],
    modifier_options: Dict[str, Any],
    visited_options: set,
) -> bool:
    """Helper function to check for infinite loops in nested modifier options."""
    option_guid = option.get("guid")
    if option_guid in visited_options:
        return False  # Already checked this option in this path

    visited_options.add(option_guid)

    # Check all nested modifier groups
    for nested_modifier_ref in option.get("modifierGroupReferences", []):
        nested_mod_group = modifier_groups.get(str(nested_modifier_ref))
        if not nested_mod_group:
            continue

        # Check if any option references back to the target item
        for nested_option_ref in nested_mod_group.get("modifierOptionReferences", []):
            nested_option = modifier_options.get(str(nested_option_ref))
            if nested_option and nested_option.get("guid") == target_item_guid:
                return True

            # Continue recursively checking deeper
            if nested_option and _has_infinite_loop_in_option(
                nested_option,
                target_item_guid,
                modifier_groups,
                modifier_options,
                visited_options.copy(),
            ):
                return True

    return False


def _format_pricing_info(item: Dict[str, Any]) -> List[str]:
    """Extract and format pricing information based on pricing strategy."""
    pricing_lines = []
    pricing_strategy = item.get("pricingStrategy")
    price = item.get("price")
    pricing_rules = item.get("pricingRules") or {}
    item_name = item["name"]

    if pricing_strategy == "BASE_PRICE" and price is not None:
        pricing_lines.append(f"{item_name} Base Price: ${price}")

    elif pricing_strategy == "MENU_SPECIFIC_PRICE" and price is not None:
        pricing_lines.append(f"{item_name}: ${price}")

    elif pricing_strategy == "TIME_SPECIFIC_PRICE":
        time_rules = pricing_rules.get("timeSpecificPricingRules", [])
        if time_rules:
            pricing_lines.append(f"{item_name} Time-Specific Pricing:")
            for rule in time_rules:
                time_price = rule.get("timeSpecificPrice")
                for schedule in rule.get("schedule", []):
                    days = ", ".join(schedule.get("days", []))
                    for time_range in schedule.get("timeRanges", []):
                        start_time = time_range.get("start")
                        end_time = time_range.get("end")
                        pricing_lines.append(
                            f"  - ${time_price} ({days}: {start_time}-{end_time})"
                        )

    elif pricing_strategy == "SIZE_PRICE":
        size_pricing_guid = pricing_rules.get("sizeSpecificPricingGuid")
        if size_pricing_guid:
            pricing_lines.append(f"{item_name} Size-Based Pricing (see size modifiers)")
            pricing_lines.append(f"Size Specific Pricing GUID: {size_pricing_guid}")

    return pricing_lines


def _format_system_prompt_pricing(item: Dict[str, Any]) -> str:
    """Format pricing information for system prompt."""
    pricing_strategy = item.get("pricingStrategy")
    price = item.get("price")
    pricing_rules = item.get("pricingRules") or {}

    if pricing_strategy == "BASE_PRICE" and price is not None:
        return f"${price}"

    elif pricing_strategy == "MENU_SPECIFIC_PRICE" and price is not None:
        return f"${price}"

    elif pricing_strategy == "TIME_SPECIFIC_PRICE":
        time_rules = pricing_rules.get("timeSpecificPricingRules", [])
        if time_rules:
            pricing_parts = []
            for rule in time_rules:
                time_price = rule.get("timeSpecificPrice")
                for schedule in rule.get("schedule", []):
                    days = ", ".join(schedule.get("days", []))
                    for time_range in schedule.get("timeRanges", []):
                        start_time = time_range.get("start")
                        end_time = time_range.get("end")
                        pricing_parts.append(
                            f"${time_price} ({days}: {start_time}-{end_time})"
                        )
            return "; ".join(pricing_parts)

    elif pricing_strategy == "SIZE_PRICE":
        return "Size-based pricing (see size options)"

    return "Price varies"


def _format_nested_structured_modifiers(
    option: Dict[str, Any],
    modifier_groups: Dict[str, Any],
    modifier_options: Dict[str, Any],
    visited_options: Optional[set] = None,
    indent_level: int = 1,
) -> List[str]:
    """Format nested modifier options for structured prompt format with cycle detection.

    Args:
        option: The modifier option that may have nested modifiers
        modifier_groups: Dictionary of all modifier groups
        modifier_options: Dictionary of all modifier options
        visited_options: Set of visited option GUIDs for cycle detection
        indent_level: Current indentation level (1 = first level nested)

    Returns:
        List of formatted strings for nested modifiers with proper indentation
    """
    if visited_options is None:
        visited_options = set()

    # Prevent infinite recursion by tracking visited options
    option_guid = option.get("guid")
    if option_guid in visited_options:
        option_name = option.get("name", "customization")
        logger.debug(
            "WARNING: Circular reference detected in menu structure for '%s' (GUID: %s)",
            option_name,
            option_guid,
        )
        return []

    visited_options.add(option_guid)
    nested_modifier_info = []
    nested_modifier_refs = option.get("modifierGroupReferences", [])

    for nested_ref_id in nested_modifier_refs:
        nested_mod_group = modifier_groups.get(str(nested_ref_id))
        if not nested_mod_group:
            continue

        nested_group_name = nested_mod_group["name"]
        nested_required_mode = nested_mod_group.get("requiredMode", "UNKNOWN").lower()
        nested_min_selections = nested_mod_group.get("minSelections", 0)
        nested_max_selections = nested_mod_group.get("maxSelections")

        # Build constraint description for nested group
        nested_constraint_parts = []
        if nested_required_mode == "required":
            nested_constraint_parts.append("Required")
        else:
            nested_constraint_parts.append("Optional")

        if nested_max_selections is None:
            if nested_min_selections > 0:
                nested_constraint_parts.append(
                    f"Select {nested_min_selections}+ options"
                )
            else:
                nested_constraint_parts.append("Select any number")
        elif nested_min_selections == nested_max_selections:
            nested_constraint_parts.append(f"Select exactly {nested_min_selections}")
        else:
            nested_constraint_parts.append(
                f"Select {nested_min_selections}-{nested_max_selections} options"
            )

        nested_constraint_text = " (" + ", ".join(nested_constraint_parts) + ")"

        # Get nested options
        nested_options = []
        further_nested_modifiers = []

        for nested_option_ref in nested_mod_group.get("modifierOptionReferences", []):
            nested_option = modifier_options.get(str(nested_option_ref))
            if nested_option:
                nested_option_name = nested_option["name"]
                nested_option_price = nested_option.get("price")
                if nested_option_price is not None:
                    nested_options.append(
                        f"{nested_option_name} (+${nested_option_price:.2f})"
                    )
                else:
                    nested_options.append(nested_option_name)

                # Recursively handle further nesting (with cycle detection)
                further_nested = _format_nested_structured_modifiers(
                    nested_option,
                    modifier_groups,
                    modifier_options,
                    visited_options.copy(),
                    indent_level + 1,
                )
                further_nested_modifiers.extend(further_nested)

        # Format this nested group with proper indentation
        # Base indent is 2 spaces, each level adds 2 more
        indent = "  " * (indent_level + 1)
        if nested_options:
            nested_modifier_info.append(
                f"{indent}- {nested_group_name}{nested_constraint_text}: {', '.join(nested_options)}"
            )
        else:
            nested_modifier_info.append(
                f"{indent}- {nested_group_name}{nested_constraint_text}"
            )

        # Add any further nested modifiers
        nested_modifier_info.extend(further_nested_modifiers)

    return nested_modifier_info


def _format_structured_modifiers(
    item: Dict[str, Any],
    modifier_groups: Dict[str, Any],
    modifier_options: Dict[str, Any],
) -> List[str]:
    """Format modifier information for structured prompt format (bullet points).

    Args:
        item: Menu item dictionary
        modifier_groups: Dictionary of all modifier groups
        modifier_options: Dictionary of all modifier options

    Returns:
        List of formatted modifier strings with bullet points
    """
    modifier_info = []
    modifier_refs = item.get("modifierGroupReferences", [])

    for ref_id in modifier_refs:
        mod_group = modifier_groups.get(str(ref_id))
        if not mod_group:
            continue

        mod_group_name = mod_group["name"]
        required_mode = mod_group.get("requiredMode", "UNKNOWN").lower()
        min_selections = mod_group.get("minSelections", 0)
        max_selections = mod_group.get("maxSelections")
        pricing_strategy = mod_group.get("pricingStrategy")

        # Build constraint description
        constraint_parts = []
        if required_mode == "required":
            constraint_parts.append("Required")
        else:
            constraint_parts.append("Optional")

        if max_selections is None:
            if min_selections > 0:
                constraint_parts.append(f"Select {min_selections}+ options")
            else:
                constraint_parts.append("Select any number")
        elif min_selections == max_selections:
            constraint_parts.append(f"Select exactly {min_selections}")
        else:
            constraint_parts.append(f"Select {min_selections}-{max_selections} options")

        constraint_text = " (" + ", ".join(constraint_parts) + ")"

        # Get options - separate those with nested modifiers from those without
        options_without_nested = []
        options_with_nested = []

        for option_ref in mod_group.get("modifierOptionReferences", []):
            option = modifier_options.get(str(option_ref))
            if option:
                option_name = option["name"]
                option_price = option.get("price")

                # Format option display string (skip sequence pricing details)
                if pricing_strategy in ["SEQUENCE_PRICE", "SIZE_SEQUENCE_PRICE"]:
                    option_display = option_name
                elif option_price is not None:
                    option_display = f"{option_name} (+${option_price:.2f})"
                else:
                    option_display = option_name

                # Check for nested modifiers on this option
                nested_modifier_info = _format_nested_structured_modifiers(
                    option, modifier_groups, modifier_options, None, 1
                )

                if nested_modifier_info:
                    # Store option with its nested modifiers
                    options_with_nested.append(
                        {"display": option_display, "nested": nested_modifier_info}
                    )
                else:
                    options_without_nested.append(option_display)

        # Format the modifier group line with only non-nested options
        if options_without_nested:
            modifier_info.append(
                f"  - {mod_group_name}{constraint_text}: {', '.join(options_without_nested)}"
            )
        elif not options_with_nested:
            # No options at all
            modifier_info.append(f"  - {mod_group_name}{constraint_text}")
        else:
            # Only has nested options - show the group header without inline options
            modifier_info.append(f"  - {mod_group_name}{constraint_text}:")

        # Add options with nested modifiers on separate lines
        for opt_with_nested in options_with_nested:
            # Show the parent option on its own line with 4-space indent
            modifier_info.append(f"    {opt_with_nested['display']}")
            # Then show its nested modifiers (they have proper indentation already)
            modifier_info.extend(opt_with_nested["nested"])

    return modifier_info


def _format_nested_modifier_options(
    option: Dict[str, Any],
    modifier_groups: Dict[str, Any],
    modifier_options: Dict[str, Any],
    indent: str = "    ",
    visited_options: Optional[set] = None,
    parent_pricing_strategy: Optional[str] = None,
) -> List[str]:
    """Format nested modifier options recursively with cycle detection."""
    if visited_options is None:
        visited_options = set()

    # Prevent infinite recursion by tracking visited options
    option_guid = option.get("guid")
    if option_guid in visited_options:
        option_name = option.get("name", "customization")
        logger.debug(
            "WARNING: Circular reference detected in menu structure for '%s' (GUID: %s)",
            option_name,
            option_guid,
        )
        return [
            f"{indent}└─ [Note: Only one {option_name} allowed per order - it is okay to order]"
        ]

    visited_options.add(option_guid)
    nested_lines = []
    nested_modifier_refs = option.get("modifierGroupReferences", [])

    for nested_ref_id in nested_modifier_refs:
        nested_mod_group = modifier_groups.get(str(nested_ref_id))
        if not nested_mod_group:
            continue

        nested_group_name = nested_mod_group["name"]
        nested_group_guid = nested_mod_group["guid"]
        nested_required_mode = nested_mod_group.get("requiredMode", "UNKNOWN").lower()
        nested_min_selections = nested_mod_group.get("minSelections", 0)
        nested_max_selections = nested_mod_group.get("maxSelections")
        nested_max_sel_text = (
            "unlimited" if nested_max_selections is None else str(nested_max_selections)
        )

        nested_lines.extend(
            [
                f"{indent}└─ Nested Modifier Group: {nested_group_name} (guid: {nested_group_guid})",
                f"{indent}   Selection Rules: {nested_required_mode}, min: {nested_min_selections}, max: {nested_max_sel_text}",
            ]
        )

        # Add nested modifier options
        for nested_option_ref in nested_mod_group.get("modifierOptionReferences", []):
            nested_option = modifier_options.get(str(nested_option_ref))
            if nested_option:
                nested_option_name = nested_option["name"]
                nested_option_price = nested_option.get("price")
                nested_option_guid = nested_option["guid"]

                if nested_option_price is not None:
                    nested_lines.append(
                        f"{indent}   - {nested_option_name}: ${nested_option_price} (guid: {nested_option_guid})"
                    )
                elif parent_pricing_strategy not in [
                    "SEQUENCE_PRICE",
                    "SIZE_SEQUENCE_PRICE",
                    "SIZE_PRICE",
                ]:
                    # Only show "Price not specified" if it's not a sequence pricing strategy
                    nested_lines.append(
                        f"{indent}   - {nested_option_name}: Price not specified (guid: {nested_option_guid})"
                    )
                else:
                    # For sequence pricing, just show the option name and GUID
                    nested_lines.append(
                        f"{indent}   - {nested_option_name} (guid: {nested_option_guid})"
                    )

                # Recursively handle further nesting if needed (with cycle detection)
                further_nested = _format_nested_modifier_options(
                    nested_option,
                    modifier_groups,
                    modifier_options,
                    indent + "    ",
                    visited_options.copy(),
                    parent_pricing_strategy,
                )
                nested_lines.extend(further_nested)

    return nested_lines


def _format_modifier_info(
    item: Dict[str, Any],
    modifier_groups: Dict[str, Any],
    modifier_options: Dict[str, Any],
) -> List[str]:
    """Extract and format modifier group information."""
    modifier_lines = []
    item_name = item["name"]
    modifier_refs = item.get("modifierGroupReferences", [])

    for ref_id in modifier_refs:
        mod_group = modifier_groups.get(str(ref_id))
        if not mod_group:
            continue

        # Extract modifier group details
        mod_group_name = mod_group["name"]
        mod_group_guid = mod_group["guid"]
        required_mode = mod_group.get("requiredMode", "UNKNOWN").lower()
        min_selections = mod_group.get("minSelections", 0)
        max_selections = mod_group.get("maxSelections")
        max_sel_text = "unlimited" if max_selections is None else str(max_selections)
        pricing_strategy = mod_group.get("pricingStrategy")

        # Add modifier group header
        modifier_lines.extend(
            [
                "",  # Empty line for spacing
                f"{item_name} Modifier Group: {mod_group_name} (guid: {mod_group_guid})",
                f"  Selection Rules: {required_mode}, min: {min_selections}, max: {max_sel_text}",
            ]
        )

        # Add sequence pricing information if available
        pricing_rules = mod_group.get("pricingRules") or {}
        sequence_rules = pricing_rules.get("sizeSequencePricingRules", [])

        if pricing_strategy in ["SEQUENCE_PRICE", "SIZE_SEQUENCE_PRICE"] or (
            pricing_strategy == "SIZE_PRICE" and sequence_rules
        ):
            if sequence_rules:
                modifier_lines.append(f"  Pricing Strategy: {pricing_strategy}")
                for rule in sequence_rules:
                    size_name = rule.get("sizeName")
                    size_guid = rule.get("sizeGuid")
                    sequence_prices = rule.get("sequencePrices", [])

                    if sequence_prices:
                        if size_name or size_guid:
                            size_display = size_name or size_guid
                            size_info = f" (size: {size_display}, size modifier guid: {size_guid})"
                        else:
                            size_info = ""
                        modifier_lines.append(f"  Sequence pricing{size_info}:")
                        for seq_price in sequence_prices:
                            seq_num = seq_price.get("sequence", 1)
                            price = seq_price.get("price", 0.0)
                            modifier_lines.append(f"    {seq_num}: ${price}")

                        # Add note about pricing for sequences beyond the defined ones
                        if len(sequence_prices) > 0:
                            last_price = sequence_prices[-1].get("price", 0.0)
                            last_sequence = sequence_prices[-1].get("sequence", 1)
                            if last_sequence < 10:  # Only show if it's reasonable
                                modifier_lines.append(
                                    f"    {last_sequence + 1}+: ${last_price} (same as last sequence)"
                                )
        elif pricing_strategy:
            modifier_lines.append(f"  Pricing Strategy: {pricing_strategy}")

        # Add modifier options
        for option_ref in mod_group.get("modifierOptionReferences", []):
            option = modifier_options.get(str(option_ref))
            if option:
                option_name = option["name"]
                option_price = option.get("price")
                option_guid = option["guid"]
                if option_price is not None:
                    modifier_lines.append(
                        f"  - {option_name}: ${option_price} (guid: {option_guid})"
                    )
                elif pricing_strategy not in [
                    "SEQUENCE_PRICE",
                    "SIZE_SEQUENCE_PRICE",
                ] and not (pricing_strategy == "SIZE_PRICE" and sequence_rules):
                    # Only show "Price not specified" if it's not a sequence pricing strategy
                    modifier_lines.append(
                        f"  - {option_name}: Price not specified (guid: {option_guid})"
                    )
                else:
                    # For sequence pricing, just show the option name and GUID
                    modifier_lines.append(f"  - {option_name} (guid: {option_guid})")

                # Handle nested modifiers for this option
                nested_modifier_lines = _format_nested_modifier_options(
                    option,
                    modifier_groups,
                    modifier_options,
                    "    ",
                    None,
                    pricing_strategy,
                )
                modifier_lines.extend(nested_modifier_lines)

    return modifier_lines


def _process_menu_item(
    item: Dict[str, Any],
    group_guid: str,
    group_name: str,
    context: str,
    modifier_groups: Dict[str, Any],
    modifier_options: Dict[str, Any],
    results: List[Dict[str, str]],
) -> None:
    """Process a single menu item and add it to results."""
    item_name = item["name"]
    item_guid = item["guid"]

    # Create item name with context at front for better identification and to avoid duplicates
    item_name_with_context = f"{context}: {item_name}" if context else item_name

    # Build output lines efficiently using list [[memory:5262012]]
    output_lines = [
        f"Item: {item_name}",
        f"Context: {context}",
        f"Item GUID: {item_guid}",
        f"Group GUID: {group_guid}",
    ]

    # Add pricing information
    output_lines.extend(_format_pricing_info(item))

    # Add modifier information
    output_lines.extend(_format_modifier_info(item, modifier_groups, modifier_options))

    # Join all lines and add to results
    result_text = "\n".join(output_lines)
    results.append({item_name_with_context: result_text})


def _process_menu_item_system_prompt(
    item: Dict[str, Any],
    group_name: str,
    context: str,
    modifier_groups: Dict[str, Any],
    modifier_options: Dict[str, Any],
    system_prompt_results: List[str],
) -> None:
    """Process a single menu item for system prompt format (structured markdown format)."""
    item_name = item["name"]
    description = item.get("description", "")

    # Build header: ### {name} - {description}
    if description:
        header = f"### {item_name} - {description}"
    else:
        header = f"### {item_name}"

    # Get pricing
    price_info = _format_system_prompt_pricing(item)
    price_line = f"Prices: {price_info}"

    # Get modifiers using structured format
    modifier_lines = _format_structured_modifiers(
        item, modifier_groups, modifier_options
    )

    # Build output
    system_prompt_results.append(header)
    system_prompt_results.append(price_line)

    if modifier_lines:
        system_prompt_results.append("Customizations:")
        system_prompt_results.extend(modifier_lines)

    # Add blank line separator
    system_prompt_results.append("")


def _process_menu_group(
    menu_group: Dict[str, Any],
    menu_name: str,
    parent_group_name: str,
    modifier_groups: Dict[str, Any],
    modifier_options: Dict[str, Any],
    results: List[Dict[str, str]],
    system_prompt_results: Optional[List[str]] = None,
    infinite_loop_items: Optional[List[Dict[str, str]]] = None,
) -> None:
    """Recursively process menu groups and their nested groups."""
    group_name = menu_group.get("name", "")
    group_guid = menu_group.get("guid", "")

    context = _build_hierarchy_context(menu_name, parent_group_name, group_name)

    # Process items in current group
    for item in menu_group.get("menuItems", []):
        # Check for infinite loops before processing
        has_infinite_loop = _has_infinite_loop(item, modifier_groups, modifier_options)

        if has_infinite_loop:
            # Add to infinite loop items instead of main results
            if infinite_loop_items is not None:
                _process_menu_item(
                    item,
                    group_guid,
                    group_name,
                    context,
                    modifier_groups,
                    modifier_options,
                    infinite_loop_items,
                )
        else:
            # Process for detailed format
            _process_menu_item(
                item,
                group_guid,
                group_name,
                context,
                modifier_groups,
                modifier_options,
                results,
            )

            # Process for system prompt format if requested (now uses structured markdown format)
            if system_prompt_results is not None:
                _process_menu_item_system_prompt(
                    item,
                    group_name,
                    context,
                    modifier_groups,
                    modifier_options,
                    system_prompt_results,
                )

    # Recursively process nested menu groups
    for nested_group in menu_group.get("menuGroups", []):
        _process_menu_group(
            nested_group,
            menu_name,
            group_name,
            modifier_groups,
            modifier_options,
            results,
            system_prompt_results,
            infinite_loop_items,
        )


def parse_menu(
    json_data: Dict[str, Any],
    selected_menus: Optional[List[str]] = None,
) -> Tuple[List[Dict[str, str]], str, List[Dict[str, str]]]:
    """
    Parse the menu JSON data and extract item details with pricing and modifier information.

    Args:
        json_data: The JSON data containing menu information returned from the Toast API.
        selected_menus: Optional list of menu names to process. If provided and not empty, only menus
                        with names in this list will be processed. If None or empty, all menus will be
                        processed.

    Returns:
        Tuple containing:
        - List of dictionaries with detailed menu information (with GUIDs)
        - String with system prompt menu in structured markdown format
        - List of dictionaries with infinite loop items (excluded from main menu)
    """
    # Load references for efficient lookup
    modifier_groups = json_data.get("modifierGroupReferences", {})
    modifier_options = json_data.get("modifierOptionReferences", {})

    results: List[Dict[str, str]] = []
    system_prompt_results: List[str] = []
    infinite_loop_items: List[Dict[str, str]] = []

    # Main processing loop
    for menu in json_data.get("menus", []):
        menu_name = menu.get("name", "")

        # Filter menus based on the selected_menus parameter
        if selected_menus is not None and len(selected_menus) > 0:
            if menu_name not in selected_menus:
                continue

        # Create temporary list to check if menu has any items [[memory:5262012]]
        temp_system_prompt_results: List[str] = []

        # Add menu-level header (markdown format)
        if menu_name:
            temp_system_prompt_results.append(f"# {menu_name}\n")

        for menu_group in menu.get("menuGroups", []):
            group_name = menu_group.get("name", "")

            # Add group-level header (markdown format)
            if group_name:
                temp_system_prompt_results.append(f"## {group_name}\n")

            _process_menu_group(
                menu_group,
                menu_name,
                "",
                modifier_groups,
                modifier_options,
                results,
                temp_system_prompt_results,
                infinite_loop_items,
            )

        # Only add menu if there are actually items in this menu
        if temp_system_prompt_results:
            system_prompt_results.extend(temp_system_prompt_results)

    # Create system prompt menu string (now uses structured markdown format)
    system_prompt_menu = "\n".join(system_prompt_results).strip()

    return results, system_prompt_menu, infinite_loop_items
