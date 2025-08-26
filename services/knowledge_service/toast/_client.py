"""
Toast API client for menu data retrieval and authentication.

This module handles external API communication with Toast's services
to fetch menu data for processing and indexing.

Key responsibilities:
- OAuth token management and authentication
- Menu metadata and menu data download from Toast API endpoints
- HTTP request handling with proper error management
- API response validation and error handling

Authentication flow:
1. Obtain bearer token using Toast API credentials
2. Call metadata endpoint to get restaurant info
3. Use token for authenticated menu API requests
4. Download and validate menu data JSON

External dependencies:
- Toast Authentication API for token management
- Toast Menu API for menu data retrieval
"""

import json
from typing import Any, Dict, Optional

from tools.toast_tool._apis._utils import connect_toast_order_hub
from tools.toast_tool.classes import ToastAccessToken
from tools.utils.ordering.classes import HttpMethod
from utils.log import logger


def get_menu_metadata(
    bearer_token: ToastAccessToken,
    restaurant_external_id: str,
    general_api_endpoint: Optional[str] = None,
) -> Dict[str, Any]:
    """Get menu metadata from Toast API.

    This endpoint should be called before downloading menu data to ensure
    we have the latest restaurant information and last updated timestamp.

    Args:
        bearer_token: The Toast access token
        restaurant_external_id: The restaurant external ID (Toast-Restaurant-External-ID header)
        general_api_endpoint: Optional custom API endpoint

    Returns:
        dict: Menu metadata containing restaurantGuid and lastUpdated

    Raises:
        RuntimeError: If metadata retrieval fails
        ValueError: If metadata data is invalid
    """
    try:
        logger.debug(
            f"[toast._client.get_menu_metadata] Getting menu metadata for restaurant {restaurant_external_id}"
        )

        # Use the Toast API utility to make the request
        response = connect_toast_order_hub(
            http_method=HttpMethod.GET,
            bearer_token=bearer_token,
            api_function="/menus/v3/metadata",
            store_id=restaurant_external_id,
            general_api_endpoint=general_api_endpoint,
        )

        if response.status == 200:
            metadata = json.loads(response.decoded_body)

            # Validate required fields
            if not metadata.get("restaurantGuid"):
                raise ValueError("Invalid metadata - missing restaurantGuid")

            logger.debug(
                f"[toast._client.get_menu_metadata] Successfully retrieved metadata for restaurant {metadata.get('restaurantGuid')}, last updated: {metadata.get('lastUpdated')}"
            )

            return metadata
        else:
            raise RuntimeError(
                f"Error getting menu metadata: {response.status} - {response.decoded_body}"
            )

    except Exception as e:
        if isinstance(e, (RuntimeError, ValueError)):
            raise
        raise RuntimeError(f"Network error getting menu metadata: {e}") from e


def download_menu(
    bearer_token: ToastAccessToken,
    restaurant_external_id: str,
    general_api_endpoint: Optional[str] = None,
) -> Dict[str, Any]:
    """Downloads menu data from Toast API.

    Args:
        bearer_token: The Toast access token
        restaurant_external_id: The restaurant external ID (Toast-Restaurant-External-ID header)
        general_api_endpoint: Optional custom API endpoint

    Returns:
        dict: The menu data from the API

    Raises:
        RuntimeError: If menu download fails
        ValueError: If menu data is invalid
    """
    try:
        logger.debug(
            f"[toast._client.download_menu] Downloading menu for restaurant {restaurant_external_id}"
        )

        # Use the Toast API utility to make the request to get the full menu
        response = connect_toast_order_hub(
            http_method=HttpMethod.GET,
            bearer_token=bearer_token,
            api_function="/menus/v3/menus",
            store_id=restaurant_external_id,
            general_api_endpoint=general_api_endpoint,
        )

        if response.status == 200:
            menu_data = json.loads(response.decoded_body)

            # Basic validation - check for required menu structure
            if not menu_data.get("menus"):
                raise ValueError("Invalid menu data - no menus found")

            logger.debug(
                f"[toast._client.download_menu] Successfully downloaded menu for restaurant {restaurant_external_id}, found {len(menu_data.get('menus', []))} menus"
            )

            return menu_data
        else:
            raise RuntimeError(
                f"Error downloading menu: {response.status} - {response.decoded_body}"
            )
    except Exception as e:
        if isinstance(e, (RuntimeError, ValueError)):
            raise
        raise RuntimeError(f"Network error downloading menu: {e}") from e
