"""
OLO API client for menu data retrieval.

This module provides functions for authenticating with and retrieving
menu data from the OLO API using signed requests.

Key responsibilities:
- OLO API authentication and request signing
- Menu data retrieval
- Product modifier data retrieval with nested support
- Request body hashing and signature creation
"""

import base64
import hashlib
import hmac
import http.client
import json
import urllib.parse
from email.utils import formatdate
from typing import Any, Dict, Optional

from utils.log import logger


def _hash_request_body(body: str) -> str:
    """Hash the request body using SHA-256 and return base64 encoded string.

    Args:
        body: Request body string to hash

    Returns:
        Base64 encoded SHA-256 hash
    """
    if not body:
        body = ""

    hash_obj = hashlib.sha256()
    hash_obj.update(body.encode("utf-8"))
    hash_bytes = hash_obj.digest()

    return base64.b64encode(hash_bytes).decode("utf-8")


def _create_signature(
    client_secret: str,
    client_id: str,
    http_verb: str,
    content_type: str,
    hashed_body: str,
    path_and_query: str,
    time_stamp: str,
) -> str:
    """Create signature for Olo API request.

    Args:
        client_secret: OLO API client secret
        client_id: OLO API client ID
        http_verb: HTTP method (GET, POST, etc.)
        content_type: Content-Type header value
        hashed_body: Base64 encoded hash of request body
        path_and_query: API path with query parameters
        time_stamp: RFC 2822 formatted timestamp

    Returns:
        Base64 encoded HMAC-SHA256 signature
    """
    string_to_sign = f"{client_id}\n{http_verb}\n{content_type}\n{hashed_body}\n{path_and_query}\n{time_stamp}"

    signature = hmac.new(
        client_secret.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha256
    ).digest()

    return base64.b64encode(signature).decode("utf-8")


def make_signed_request(
    api_function: str,
    client_id: str,
    client_secret: str,
    general_api_endpoint: Optional[str] = None,
    query_params: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Make a signed request to the Olo API.

    Args:
        api_function: API endpoint path (e.g., "/v1.1/restaurants/123/menu")
        client_id: OLO API client ID
        client_secret: OLO API client secret
        general_api_endpoint: Optional custom API endpoint. If provided, parse and use it.
                             If not provided, defaults to ordering.api.olosandbox.com
        query_params: Optional query parameters

    Returns:
        Parsed JSON response

    Raises:
        Exception: If request fails or returns non-200 status
    """
    # Use credentials passed as parameters (no longer fetching from environment)

    path_and_query = api_function
    if query_params:
        path_and_query += "?" + urllib.parse.urlencode(query_params)

    http_method = "GET"
    request_body = ""
    content_type = "application/json"

    # Parse custom endpoint or use default sandbox
    if general_api_endpoint:
        # Parse the endpoint - it may be provided as "ordering.api.olo.com" or "https://ordering.api.olo.com"
        parsed = urllib.parse.urlparse(
            general_api_endpoint
            if general_api_endpoint.startswith("http")
            else f"https://{general_api_endpoint}"
        )
        base_url = parsed.netloc
    else:
        base_url = "ordering.api.olosandbox.com"

    time_stamp = formatdate(timeval=None, localtime=False, usegmt=True)
    hashed_body = _hash_request_body(request_body)

    signed_message = _create_signature(
        client_secret=client_secret,
        client_id=client_id,
        http_verb=http_method,
        content_type=content_type,
        hashed_body=hashed_body,
        path_and_query=path_and_query,
        time_stamp=time_stamp,
    )

    headers = {
        "Authorization": f"OloSignature {client_id}:{signed_message}",
        "Date": time_stamp,
        "Content-Type": content_type,
    }

    conn = None
    try:
        conn = http.client.HTTPSConnection(base_url, timeout=30)
        conn.request(http_method, path_and_query, request_body, headers)
        response = conn.getresponse()
        response_data = response.read().decode("utf-8")

        if response.status != 200:
            raise Exception(
                f"Error: {response.status} - {response.reason} - {response_data}"
            )

        return json.loads(response_data)

    except Exception as e:
        raise Exception(f"Error calling {api_function}: {str(e)}") from e
    finally:
        if conn:
            conn.close()


def _process_modifier_option(option: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively process a modifier option and its nested modifiers.

    Args:
        option: Option dict from OLO API

    Returns:
        Processed option dict with nested modifiers
    """
    processed_option = {
        "id": option.get("id"),
        "name": option.get("name"),
        "cost": option.get("cost"),
    }

    # Recursively process nested modifiers if they exist
    if option.get("modifiers"):
        processed_option["modifiers"] = []
        for modifier in option["modifiers"]:
            processed_modifier = {
                "id": modifier.get("id"),
                "description": modifier.get("description"),
                "mandatory": modifier.get("mandatory"),
                "minselects": modifier.get("minselects"),
                "maxselects": modifier.get("maxselects"),
                "options": [],
            }

            # Process all options in this modifier group
            for sub_option in modifier.get("options", []):
                processed_modifier["options"].append(
                    _process_modifier_option(sub_option)
                )

            processed_option["modifiers"].append(processed_modifier)

    return processed_option


def _get_product_modifiers(
    product_id: int,
    client_id: str,
    client_secret: str,
    general_api_endpoint: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Fetch and process product modifiers with recursive nesting support.

    Args:
        product_id: OLO product ID
        client_id: OLO API client ID
        client_secret: OLO API client secret
        general_api_endpoint: Optional custom API endpoint

    Returns:
        Processed modifiers dict, or None if error occurs
    """
    try:
        modifiers_data = make_signed_request(
            f"/v1.1/products/{product_id}/modifiers",
            client_id,
            client_secret,
            general_api_endpoint,
        )

        # Process modifiers with recursive support
        processed_modifiers = {"optiongroups": []}

        for group in modifiers_data.get("optiongroups", []):
            processed_group = {
                "id": group.get("id"),
                "description": group.get("description"),
                "mandatory": group.get("mandatory"),
                "minselects": group.get("minselects"),
                "maxselects": group.get("maxselects"),
                "options": [],
            }

            # Process all options in this group
            for option in group.get("options", []):
                processed_group["options"].append(_process_modifier_option(option))

            processed_modifiers["optiongroups"].append(processed_group)

        return processed_modifiers
    except Exception as e:
        logger.debug(
            f"[olo._client._get_product_modifiers] Error fetching modifiers for product {product_id}: {str(e)}"
        )
        return None


def _process_category_products(
    category: Dict[str, Any],
    client_id: str,
    client_secret: str,
    general_api_endpoint: Optional[str] = None,
    check_availability: bool = True,
) -> list[Dict[str, Any]]:
    """Process products in a category, fetching modifiers for each.

    Args:
        category: Category dict from OLO API
        client_id: OLO API client ID
        client_secret: OLO API client secret
        general_api_endpoint: Optional custom API endpoint
        check_availability: Whether to skip disabled products

    Returns:
        List of products with their modifiers
    """
    products_with_modifiers = []
    for product in category.get("products", []):
        # Skip disabled products if checking availability
        if check_availability:
            product_availability = product.get("availability", {})
            if product_availability.get("isdisabled"):
                continue

        product_id = product.get("id")
        logger.debug(
            f"[olo._client._process_category_products] Fetching modifiers for {product.get('name')} (ID: {product_id})"
        )

        # Fetch modifiers for this product
        modifiers = _get_product_modifiers(
            product_id, client_id, client_secret, general_api_endpoint
        )

        # Build product dict with modifiers
        product_with_modifiers = dict(product)
        product_with_modifiers["modifiers"] = modifiers

        products_with_modifiers.append(product_with_modifiers)

    return products_with_modifiers


def _transform_menu_response(
    raw_menu: Dict[str, Any],
    client_id: str,
    client_secret: str,
    general_api_endpoint: Optional[str] = None,
) -> Dict[str, Any]:
    """Transform raw OLO API menu response to expected format.

    The raw API returns categories as a list of category objects with products.
    This function transforms it to a dict mapping category names to product lists,
    and fetches modifiers for each product.

    Args:
        raw_menu: Raw menu data from OLO API with categories as list
        client_id: OLO API client ID
        client_secret: OLO API client secret
        general_api_endpoint: Optional custom API endpoint

    Returns:
        Transformed menu data with categories as dict and products with modifiers
    """
    transformed = {"categories": {}, "single_use_categories": {}}

    # Process regular categories (list -> dict)
    for category in raw_menu.get("categories", []):
        category_name = category.get("name")
        if not category_name:
            continue

        products_with_modifiers = _process_category_products(
            category,
            client_id,
            client_secret,
            general_api_endpoint,
            check_availability=True,
        )
        transformed["categories"][category_name] = products_with_modifiers

    # Process single use categories (list -> dict)
    for category in raw_menu.get("singleusecategories", []):
        category_name = category.get("name")
        if not category_name:
            continue

        products_with_modifiers = _process_category_products(
            category,
            client_id,
            client_secret,
            general_api_endpoint,
            check_availability=False,
        )
        transformed["single_use_categories"][category_name] = products_with_modifiers

    return transformed


def get_restaurant_menu(
    restaurant_id: str,
    client_id: str,
    client_secret: str,
    general_api_endpoint: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Fetch restaurant menu from Olo API using signed authentication.

    This function fetches the menu and all product modifiers, transforming
    the raw API response into the expected format for menu processing.

    Args:
        restaurant_id: OLO restaurant ID
        client_id: OLO API client ID
        client_secret: OLO API client secret
        general_api_endpoint: Optional custom API endpoint

    Returns:
        Transformed menu data dict with categories as dicts and products with modifiers,
        or None if error occurs
    """
    try:
        raw_menu = make_signed_request(
            f"/v1.1/restaurants/{restaurant_id}/menu",
            client_id,
            client_secret,
            general_api_endpoint,
            {"includedisabled": "false", "deliverymode": "delivery"},
        )
        # Transform the raw API response to expected format (fetches modifiers for each product)
        return _transform_menu_response(
            raw_menu, client_id, client_secret, general_api_endpoint
        )
    except Exception as e:
        logger.debug(
            f"[olo._client.get_restaurant_menu] Error fetching menu for restaurant {restaurant_id}: {str(e)}"
        )
        return None
