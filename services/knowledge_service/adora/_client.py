"""
Adora API client for menu data retrieval and authentication.

This module handles all external API communication with Adora's services
to fetch menu data for processing and indexing.

Key responsibilities:
- OAuth token management and authentication
- Menu data download from Adora API endpoints
- HTTP request handling with proper error management
- API response validation and error handling

Authentication flow:
1. Obtain bearer token using client credentials
2. Use token for authenticated API requests
3. Download and validate menu data JSON

External dependencies:
- Adora Token API for authentication
- Adora Menu API for menu data retrieval
"""

from typing import Any, Dict

import requests

from utils.log import logger


def get_bearer_token(
    client_id: str,
    client_secret: str,
    token_api_endpoint: str,
) -> str:
    """Get bearer token from Adora API.

    Args:
        client_id: Client ID for authentication
        client_secret: Client secret for authentication
        token_api_endpoint: Complete URL for the token endpoint

    Returns:
        str: Bearer token for API authentication

    Raises:
        RuntimeError: If token retrieval fails
    """
    token_url = token_api_endpoint

    payload = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }

    try:
        logger.debug(
            f"[adora_client.get_bearer_token] Requesting bearer token from {token_url}"
        )
        response = requests.post(token_url, data=payload, timeout=10)
        response.raise_for_status()
        token = response.json().get("access_token")
        if not token:
            raise ValueError("No access token received")
        return token
    except requests.exceptions.HTTPError as err:
        raise RuntimeError(
            f"Error getting token: {err.response.status_code} {err.response.reason}"
        )
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Network error getting token: {e}")


def download_menu(
    store_id: str,
    token: str,
    general_api_endpoint: str,
) -> Dict[str, Any]:
    """Downloads menu data from Adora API.

    Args:
        store_id: The store ID to download menu for
        token: The bearer token for authentication
        general_api_endpoint: The complete URL for the general API endpoint
            (e.g., "https://public.api.adorapos.net/api/v1/OrderHub")

    Returns:
        dict: The menu data from the API

    Raises:
        RuntimeError: If menu download fails
        ValueError: If menu data is invalid
    """

    headers = {"Authorization": f"Bearer {token}"}
    params = {"sid": store_id}
    menu_url = (
        general_api_endpoint + "menu"
        if general_api_endpoint.endswith("/")
        else general_api_endpoint + "/menu"
    )
    try:
        logger.debug(
            f"[adora_client.download_menu] Downloading menu for store {store_id}"
        )
        response = requests.get(menu_url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        menu_data = response.json()

        # Validate menu data
        if (
            menu_data.get("latitude", 0.0) == 0.0
            and menu_data.get("longitude", 0.0) == 0.0
        ):
            raise ValueError("Invalid menu data - check store ID and credentials")

        return menu_data
    except requests.exceptions.HTTPError as err:
        raise RuntimeError(
            f"Error downloading menu: {err.response.status_code} {err.response.reason}"
        )
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Network error downloading menu: {e}")
