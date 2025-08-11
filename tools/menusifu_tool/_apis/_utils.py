import http.client
import urllib.parse
from typing import Dict, Optional

from pydantic import ValidationError

from utils.log import logger


class MenuSifuAPIError(Exception):
    """Custom exception for MenuSifu API errors"""

    pass


def parse_json(model_class, json_str: str):
    """
    Try to parse the JSON string into the model class.
    If it fails, print the error and return None.
    """
    try:
        data_model = model_class.model_validate_json(json_str)
        return data_model
    except ValidationError as e:
        logger.error(e)
    return None


def connect_menusifu_api(
    http_method: str,
    access_token: str,
    api_endpoint: str,
    query_params: Optional[Dict] = None,
    extra_headers: Optional[Dict] = None,
    payload: Optional[str] = "",
    base_url: str = "assistant.mealkeyway.com",
) -> Dict:
    """
    Utility function to connect to MenuSifu API

    Args:
        http_method: HTTP method (GET, POST, etc.)
        access_token: MenuSifu API access token
        api_endpoint: API endpoint path (e.g., "/bot/merchant/{merchantId}/menu")
        query_params: Optional query parameters
        extra_headers: Optional extra headers
        payload: Request payload for POST requests
        base_url: Base URL for MenuSifu API

    Returns:
        Dict: Response with status, reason, and decoded_body

    Raises:
        ValueError: If the HTTP method is invalid or the request fails
    """
    valid_methods = ["GET", "POST", "PUT", "DELETE"]
    if http_method.upper() not in valid_methods:
        raise ValueError(
            f"Invalid HTTP method: {http_method}. Must be one of {valid_methods}"
        )

    try:
        # Create connection
        conn = http.client.HTTPSConnection(base_url)

        try:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
            }
            if extra_headers:
                headers.update(extra_headers)

            path_plus_params = api_endpoint

            if query_params:
                path_plus_params = (
                    path_plus_params + "?" + urllib.parse.urlencode(query_params)
                )

            # Make request
            conn.request(http_method.upper(), path_plus_params, payload, headers)

            # Get response
            res = conn.getresponse()
            data = res.read()
            response_body = data.decode("utf-8")

            api_response = {
                "status": res.status,
                "reason": res.reason,
                "decoded_body": response_body,
            }

            return api_response

        finally:
            # Ensure connection is always closed
            conn.close()

    except Exception as e:
        error_msg = f"Failed to connect to MenuSifu API: {str(e)}"
        logger.error(error_msg)
        raise ValueError(error_msg)
