"""
Square API client for menu data retrieval and authentication.

This module handles all external API communication with Square's services
to fetch menu data for processing and indexing.

Key responsibilities:
- Menu data download from Square Catalog API
- Location-specific filtering and validation
- HTTP request handling with proper error management
- API response validation and error handling

External dependencies:
- Square Catalog API for menu data retrieval
"""

from typing import Any, Dict, List, Optional

from tools.square_tool._apis import get_catalog_object, list_catalog
from tools.square_tool._utils import get_item_variation_id
from tools.square_tool.classes import (
    CatalogItemObject,
    GetCatalogObjectInput,
    ListCatalogInput,
    SquareAccessToken,
)
from utils.log import logger


def download_menu(
    access_token: str,
    location_id: str,
    location_name: Optional[str] = None,
    default_currency: str = "USD",
) -> Dict[str, Any]:
    """Downloads menu data from Square Catalog API.

    Args:
        access_token: The Square access token for authentication
        location_id: The Square location ID to filter menu items
        location_name: Optional location name for logging (defaults to location_id)
        default_currency: Default currency code to use when none is specified (defaults to "USD")

    Returns:
        dict: The processed menu data with items and modifiers

    Raises:
        RuntimeError: If menu download fails
        ValueError: If menu data is invalid
    """
    if not location_name:
        location_name = location_id

    square_token = SquareAccessToken(access_token=access_token, token_type="Bearer")

    try:
        logger.debug(
            f"[square_client.download_menu] Downloading menu for location {location_id}"
        )

        # Get all catalog objects using pagination
        all_catalog_objects = []
        cursor = None
        page_count = 0

        while True:
            page_count += 1
            logger.debug(f"Fetching page {page_count}...")

            list_input = ListCatalogInput(cursor=cursor, use_production=True)  # type: ignore
            catalog_response = list_catalog(square_token, list_input)

            if catalog_response.objects:
                all_catalog_objects.extend(catalog_response.objects)
                logger.debug(
                    f"Got {len(catalog_response.objects)} objects on page {page_count}"
                )

            # Check if there are more pages
            if hasattr(catalog_response, "cursor") and catalog_response.cursor:
                cursor = catalog_response.cursor
            else:
                logger.debug("No more pages")
                break

        logger.debug(
            f"Total objects fetched: {len(all_catalog_objects)} across {page_count} pages"
        )

        # Filter and process items for the specified location
        processed_menu = _process_menu_items(
            square_token,
            all_catalog_objects,
            location_id,
            default_currency,
        )

        return {
            "location_id": location_id,
            "location_name": location_name,
            "total_objects": len(all_catalog_objects),
            "menu_items": processed_menu,
            "item_count": len(processed_menu),
        }

    except Exception as e:
        raise RuntimeError(f"Error downloading Square menu: {e}")


def _process_menu_items(
    access_token: SquareAccessToken,
    catalog_objects: List,
    location_id: str,
    default_currency: str = "USD",
) -> List[Dict[str, Any]]:
    """Process catalog objects to extract menu items for a specific location.

    Args:
        access_token: Square access token object
        catalog_objects: List of catalog objects from Square API
        location_id: Target location ID for filtering
        default_currency: Default currency code to use when none is specified

    Returns:
        List of processed menu items with modifiers
    """
    logger.debug(f"Processing menu items for location {location_id}")

    # Step 1: Get all items available at the location
    location_items = []

    for obj in catalog_objects:
        if obj.type == "ITEM" and isinstance(obj, CatalogItemObject):
            # Check location availability
            is_available = _is_item_available_at_location(obj, location_id)

            if is_available:
                # Check if item should be excluded
                item_name = obj.item_data.name or ""
                is_curbside_item = "curbside pickup" in item_name.lower()
                has_ume_tag = "[ume]" in item_name.lower()

                if not is_curbside_item and not has_ume_tag:
                    # Get item price
                    price_info = _get_item_price(obj, location_id, default_currency)

                    # Extract all available item data without omitting anything
                    item_data = {
                        "id": obj.id,
                        "name": obj.item_data.name or "Unnamed Item",
                        "description": getattr(obj.item_data, "description", None),
                        "price": price_info,
                    }

                    # Add any additional fields that might be available
                    label_color = getattr(obj.item_data, "label_color", None)
                    if label_color:
                        item_data["label_color"] = label_color

                    available_online = getattr(obj.item_data, "available_online", None)
                    if available_online is not None:
                        item_data["available_online"] = available_online

                    available_for_pickup = getattr(
                        obj.item_data, "available_for_pickup", None
                    )
                    if available_for_pickup is not None:
                        item_data["available_for_pickup"] = available_for_pickup

                    available_electronically = getattr(
                        obj.item_data, "available_electronically", None
                    )
                    if available_electronically is not None:
                        item_data["available_electronically"] = available_electronically

                    # Add category information if available
                    category_id = getattr(obj.item_data, "category_id", None)
                    if category_id:
                        item_data["category_id"] = category_id

                    # Add abbreviation if available
                    abbreviation = getattr(obj.item_data, "abbreviation", None)
                    if abbreviation:
                        item_data["abbreviation"] = abbreviation

                    location_items.append(item_data)
                else:
                    exclusion_reason = []
                    if is_curbside_item:
                        exclusion_reason.append("curbside pickup")
                    if has_ume_tag:
                        exclusion_reason.append("[ume] tag")

                    reason_text = " and ".join(exclusion_reason)
                    logger.debug(
                        f"Item '{obj.item_data.name}' excluded ({reason_text})"
                    )

    logger.debug(
        f"Found {len(location_items)} items available at location {location_id}"
    )

    # Step 2: Get detailed information including modifiers for each item
    final_menu = []

    for i, item in enumerate(location_items):
        logger.debug(f"Processing item {i+1}/{len(location_items)}: {item['name']}")

        # Get detailed item information
        try:
            get_input = GetCatalogObjectInput(
                object_id=item["id"],
                catalog_version=None,
                include_related_objects=True,
                include_category_path_to_root=True,
                use_production=True,
            )

            detailed_response = get_catalog_object(access_token, get_input)

            if detailed_response and detailed_response.object:
                item_obj = detailed_response.object

                # Process modifiers for this item
                location_modifiers = _process_item_modifiers(
                    item_obj,
                    detailed_response.related_objects,
                    location_id,
                    default_currency,
                )

                # Get variation ID for indexing (but don't include in final structure)
                variation_id = None
                try:
                    variation_id = get_item_variation_id(access_token, item["id"], True)
                except Exception as e:
                    logger.debug(
                        f"Error getting variation ID for item '{item['name']}': {e}"
                    )

                final_menu.append(
                    {
                        "id": item["id"],
                        "name": item["name"],
                        "description": item["description"],
                        "price": item["price"],
                        "modifiers": location_modifiers,
                        "_variation_id": variation_id,  # Keep for indexing but prefix with _
                    }
                )

        except Exception as e:
            logger.debug(f"Error processing item '{item['name']}': {e}")
            # Add item without detailed modifiers
            final_menu.append(
                {
                    "id": item["id"],
                    "name": item["name"],
                    "description": item["description"],
                    "price": item["price"],
                    "modifiers": [],
                }
            )

    return final_menu


def _is_item_available_at_location(
    item_obj: CatalogItemObject, location_id: str
) -> bool:
    """Check if an item is available at the specified location.

    Args:
        item_obj: Catalog item object
        location_id: Target location ID

    Returns:
        bool: True if item is available at location
    """
    present_at_all_locations = getattr(item_obj, "present_at_all_locations", False)
    present_at_location_ids = getattr(item_obj, "present_at_location_ids", []) or []
    absent_at_location_ids = getattr(item_obj, "absent_at_location_ids", []) or []

    return (
        present_at_all_locations and location_id not in absent_at_location_ids
    ) or location_id in present_at_location_ids


def _get_item_price(
    item_obj: CatalogItemObject, location_id: str, default_currency: str = "USD"
) -> str:
    """Get the price information for an item at a specific location.

    Args:
        item_obj: Catalog item object
        location_id: Target location ID
        default_currency: Default currency code to use when none is specified

    Returns:
        str: Formatted price string
    """
    price_info = ""

    if hasattr(item_obj.item_data, "variations") and item_obj.item_data.variations:
        first_variation = item_obj.item_data.variations[0]
        if (
            hasattr(first_variation, "item_variation_data")
            and first_variation.item_variation_data
        ):
            var_data = first_variation.item_variation_data

            # Check for location-specific price overrides first
            location_overrides = getattr(var_data, "location_overrides", []) or []
            location_price_found = False

            for override in location_overrides:
                if getattr(override, "location_id", None) == location_id:
                    if hasattr(override, "price_money") and override.price_money:
                        price = override.price_money.amount / 100
                        currency = getattr(
                            override.price_money, "currency", default_currency
                        )
                        price_info = f"${price:.2f} {currency}"
                        location_price_found = True
                        break

            # If no location override found, use default price
            if (
                not location_price_found
                and hasattr(var_data, "price_money")
                and var_data.price_money
            ):
                price = var_data.price_money.amount / 100
                currency = getattr(var_data.price_money, "currency", default_currency)
                price_info = f"${price:.2f} {currency}"

    return price_info


def _process_item_modifiers(
    item_obj,
    related_objects: Optional[List],
    location_id: str,
    default_currency: str = "USD",
) -> List[Dict[str, Any]]:
    """Process modifiers for an item at a specific location.

    Args:
        item_obj: Catalog item object
        related_objects: Related objects from the detailed response
        location_id: Target location ID
        default_currency: Default currency code to use when none is specified

    Returns:
        List of modifier groups available at the location
    """
    location_modifiers = []

    if (
        item_obj.type == "ITEM"
        and isinstance(item_obj, CatalogItemObject)
        and item_obj.item_data
    ):
        modifier_list_info = getattr(item_obj.item_data, "modifier_list_info", None)

        if modifier_list_info and related_objects:
            logger.debug(f"Found {len(modifier_list_info)} modifier list(s) for item")

            # Process each modifier list
            for mod_list_ref in modifier_list_info:
                modifier_list_id = mod_list_ref.modifier_list_id

                # Find the corresponding modifier list in related_objects
                for related_obj in related_objects:
                    if (
                        related_obj.type == "MODIFIER_LIST"
                        and related_obj.id == modifier_list_id
                    ):
                        mod_list_data = getattr(related_obj, "modifier_list_data", None)
                        if mod_list_data:
                            # Process modifiers in this list
                            modifiers_info = []
                            has_location_modifiers = False

                            if mod_list_data.modifiers:
                                for modifier_obj in mod_list_data.modifiers:
                                    # Check modifier availability at location
                                    is_available = _is_modifier_available_at_location(
                                        modifier_obj, location_id
                                    )

                                    if is_available:
                                        has_location_modifiers = True
                                        mod_data = getattr(
                                            modifier_obj, "modifier_data", None
                                        )
                                        if mod_data:
                                            # Get modifier price info
                                            price_info = ""
                                            if mod_data.price_money:
                                                price = (
                                                    mod_data.price_money.amount / 100
                                                )
                                                currency = getattr(
                                                    mod_data.price_money,
                                                    "currency",
                                                    default_currency,
                                                )
                                                if price > 0:
                                                    price_info = (
                                                        f" (+{currency} ${price:.2f})"
                                                    )
                                                elif price < 0:
                                                    price_info = f" (-{currency} ${abs(price):.2f})"

                                            modifiers_info.append(
                                                {
                                                    "id": modifier_obj.id,
                                                    "name": mod_data.name,
                                                    "price_info": price_info,
                                                }
                                            )

                            # Add modifier list if it has location-available modifiers
                            if has_location_modifiers:
                                location_modifiers.append(
                                    {
                                        "list_name": mod_list_data.name,
                                        "modifiers": modifiers_info,
                                    }
                                )
                        break

    return location_modifiers


def _is_modifier_available_at_location(modifier_obj, location_id: str) -> bool:
    """Check if a modifier is available at the specified location.

    Args:
        modifier_obj: Modifier object
        location_id: Target location ID

    Returns:
        bool: True if modifier is available at location
    """
    present_at_all_locations = getattr(modifier_obj, "present_at_all_locations", False)
    present_at_location_ids = getattr(modifier_obj, "present_at_location_ids", []) or []
    absent_at_location_ids = getattr(modifier_obj, "absent_at_location_ids", []) or []

    return (
        present_at_all_locations and location_id not in absent_at_location_ids
    ) or location_id in present_at_location_ids
