"""
Square menu processing utilities.

This module provides utility functions for processing and validating
Square menu data before indexing.

Key responsibilities:
- Data validation and sanitization
- Menu item data parsing and extraction
- Location-specific filtering helpers
- Price and modifier data processing
"""

from typing import Any, Dict, List

from utils.log import logger


def validate_square_credentials(
    access_token: str,
    location_id: str,
) -> Dict[str, Any]:
    """Validate Square API credentials and location access.

    Args:
        access_token: Square access token
        location_id: Square location ID

    Returns:
        dict: Validation results including success status and details

    Raises:
        ValueError: If credentials are invalid
    """
    if not access_token or not access_token.strip():
        return {
            "valid": False,
            "error": "Access token is required",
            "details": "Square access token cannot be empty",
        }

    if not location_id or not location_id.strip():
        return {
            "valid": False,
            "error": "Location ID is required",
            "details": "Square location ID cannot be empty",
        }

    # Basic format validation
    if len(access_token) < 10:
        return {
            "valid": False,
            "error": "Invalid access token format",
            "details": "Access token appears to be too short",
        }

    if len(location_id) < 5:
        return {
            "valid": False,
            "error": "Invalid location ID format",
            "details": "Location ID appears to be too short",
        }

    return {
        "valid": True,
        "access_token_length": len(access_token),
        "location_id": location_id,
        "details": "Basic validation passed",
    }


def parse_menu_data(raw_menu_data: Dict[str, Any]) -> Dict[str, Any]:
    """Parse and validate raw menu data from Square API.

    Args:
        raw_menu_data: Raw menu data dictionary from Square API response

    Returns:
        dict: Parsed and validated menu data

    Raises:
        ValueError: If menu data is invalid or malformed
    """
    if not isinstance(raw_menu_data, dict):
        raise ValueError("Menu data must be a dictionary")

    # Extract required fields with defaults
    location_id = raw_menu_data.get("location_id")
    if not location_id:
        raise ValueError("Menu data missing required location_id")

    location_name = raw_menu_data.get("location_name", location_id)
    menu_items = raw_menu_data.get("menu_items", [])

    if not isinstance(menu_items, list):
        raise ValueError("Menu items must be a list")

    # Validate each menu item
    validated_items = []
    for i, item in enumerate(menu_items):
        try:
            validated_item = _validate_menu_item(item)
            validated_items.append(validated_item)
        except ValueError as e:
            logger.warning(f"Skipping invalid menu item {i}: {e}")
            continue

    return {
        "location_id": location_id,
        "location_name": location_name,
        "menu_items": validated_items,
        "item_count": len(validated_items),
        "total_objects": raw_menu_data.get("total_objects", 0),
        "original_item_count": len(menu_items),
        "validation_summary": {
            "items_processed": len(menu_items),
            "items_valid": len(validated_items),
            "items_invalid": len(menu_items) - len(validated_items),
        },
    }


def _validate_menu_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a single menu item.

    Args:
        item: Menu item dictionary

    Returns:
        dict: Validated menu item

    Raises:
        ValueError: If item is invalid
    """
    if not isinstance(item, dict):
        raise ValueError("Menu item must be a dictionary")

    # Required fields
    item_id = item.get("id")
    if not item_id:
        raise ValueError("Menu item missing required ID")

    item_name = item.get("name")
    if not item_name or not item_name.strip():
        raise ValueError("Menu item missing required name")

    # Optional fields with validation
    description = item.get("description")
    if description and not isinstance(description, str):
        description = str(description)

    price = item.get("price", "")
    if price and not isinstance(price, str):
        price = str(price)

    modifiers = item.get("modifiers", [])

    if not isinstance(modifiers, list):
        modifiers = []

    # Validate modifiers
    validated_modifiers = []
    for modifier_group in modifiers:
        try:
            validated_group = _validate_modifier_group(modifier_group)
            validated_modifiers.append(validated_group)
        except ValueError as e:
            logger.debug(f"Skipping invalid modifier group for item '{item_name}': {e}")
            continue

    return {
        "id": item_id,
        "name": item_name.strip(),
        "description": description.strip() if description else None,
        "price": price.strip() if price else "",
        "modifiers": validated_modifiers,
    }


def _validate_modifier_group(modifier_group: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a modifier group.

    Args:
        modifier_group: Modifier group dictionary

    Returns:
        dict: Validated modifier group

    Raises:
        ValueError: If modifier group is invalid
    """
    if not isinstance(modifier_group, dict):
        raise ValueError("Modifier group must be a dictionary")

    list_name = modifier_group.get("list_name")
    if not list_name or not list_name.strip():
        raise ValueError("Modifier group missing required list_name")

    modifiers = modifier_group.get("modifiers", [])
    if not isinstance(modifiers, list):
        modifiers = []

    # Validate individual modifiers
    validated_modifiers = []
    for modifier in modifiers:
        try:
            validated_modifier = _validate_modifier(modifier)
            validated_modifiers.append(validated_modifier)
        except ValueError as e:
            logger.debug(f"Skipping invalid modifier in group '{list_name}': {e}")
            continue

    return {"list_name": list_name.strip(), "modifiers": validated_modifiers}


def _validate_modifier(modifier: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a single modifier.

    Args:
        modifier: Modifier dictionary

    Returns:
        dict: Validated modifier

    Raises:
        ValueError: If modifier is invalid
    """
    if not isinstance(modifier, dict):
        raise ValueError("Modifier must be a dictionary")

    modifier_id = modifier.get("id")
    if not modifier_id:
        raise ValueError("Modifier missing required ID")

    modifier_name = modifier.get("name")
    if not modifier_name or not modifier_name.strip():
        raise ValueError("Modifier missing required name")

    price_info = modifier.get("price_info", "")
    if price_info and not isinstance(price_info, str):
        price_info = str(price_info)

    return {
        "id": modifier_id,
        "name": modifier_name.strip(),
        "price_info": price_info.strip() if price_info else "",
    }


def filter_items_by_availability(
    menu_items: List[Dict[str, Any]],
    location_id: str,
) -> List[Dict[str, Any]]:
    """Filter menu items based on location availability.

    Args:
        menu_items: List of menu items
        location_id: Target location ID

    Returns:
        list: Filtered menu items available at the location
    """
    available_items = []

    for item in menu_items:
        # For processed menu items, they should already be filtered by location
        # This is an additional safety check
        item_name = item.get("name", "Unknown")

        # Check for exclusion patterns
        name_lower = item_name.lower()
        is_curbside = "curbside pickup" in name_lower
        has_ume_tag = "[ume]" in name_lower

        if not is_curbside and not has_ume_tag:
            available_items.append(item)
        else:
            logger.debug(f"Filtered out item '{item_name}' for location {location_id}")

    return available_items


def calculate_menu_statistics(menu_data: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate statistics about the menu data.

    Args:
        menu_data: Processed menu data

    Returns:
        dict: Menu statistics
    """
    menu_items = menu_data.get("menu_items", [])

    # Basic counts
    total_items = len(menu_items)
    items_with_modifiers = sum(1 for item in menu_items if item.get("modifiers"))
    items_without_modifiers = total_items - items_with_modifiers

    # Modifier statistics
    total_modifier_groups = sum(len(item.get("modifiers", [])) for item in menu_items)
    total_modifiers = sum(
        sum(len(group.get("modifiers", [])) for group in item.get("modifiers", []))
        for item in menu_items
    )

    # Price statistics
    priced_items = [item for item in menu_items if item.get("price")]
    prices = []

    for item in priced_items:
        price_str = item.get("price", "")
        if "$" in price_str:
            try:
                price_value = float(price_str.split("$")[1].split()[0])
                prices.append(price_value)
            except (ValueError, IndexError):
                continue

    price_stats = {}
    if prices:
        price_stats = {
            "min_price": min(prices),
            "max_price": max(prices),
            "avg_price": sum(prices) / len(prices),
            "items_with_price": len(prices),
        }

    return {
        "location_id": menu_data.get("location_id"),
        "location_name": menu_data.get("location_name"),
        "total_items": total_items,
        "items_with_modifiers": items_with_modifiers,
        "items_without_modifiers": items_without_modifiers,
        "total_modifier_groups": total_modifier_groups,
        "total_modifiers": total_modifiers,
        "price_statistics": price_stats,
        "total_catalog_objects": menu_data.get("total_objects", 0),
    }


def sanitize_text_content(text: str) -> str:
    """Sanitize text content for vector indexing.

    Args:
        text: Raw text content

    Returns:
        str: Sanitized text suitable for indexing
    """
    if not text:
        return ""

    # Remove excessive whitespace
    sanitized = " ".join(text.split())

    # Remove or replace problematic characters
    sanitized = sanitized.replace("\x00", "")  # Remove null bytes
    sanitized = sanitized.replace("\r\n", "\n")  # Normalize line endings
    sanitized = sanitized.replace("\r", "\n")  # Normalize line endings

    # Limit length to prevent extremely long documents
    max_length = 50000  # Adjust as needed
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length] + "... [truncated]"
        logger.warning(f"Text content truncated to {max_length} characters")

    return sanitized
