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


def get_restaurant_menu(
    restaurant_id: str,
    client_id: str,
    client_secret: str,
    general_api_endpoint: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Fetch restaurant menu from Olo API using signed authentication.

    Args:
        restaurant_id: OLO restaurant ID
        client_id: OLO API client ID
        client_secret: OLO API client secret
        general_api_endpoint: Optional custom API endpoint

    Returns:
        Menu data dict, or None if error occurs
    """
    try:
        return make_signed_request(
            f"/v1.1/restaurants/{restaurant_id}/menu",
            client_id,
            client_secret,
            general_api_endpoint,
            {"includedisabled": "false", "deliverymode": "delivery"},
        )
    except Exception as e:
        logger.debug(
            f"[olo._client.get_restaurant_menu] Error fetching menu for restaurant {restaurant_id}: {str(e)}"
        )
        return None
