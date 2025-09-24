import http.client
import json
from typing import Dict, Optional
from urllib.parse import urlencode

from tools.yelp_credit_card_tool.classes import YelpAccessToken, YelpApiResponse
from utils.log import logger

# Yelp API configuration
YELP_API_HOST = "api.yelp.com"
DEFAULT_TIMEOUT = 30  # 30 seconds default timeout


def connect_yelp_api(
    http_method: str,
    api_function: str,
    api_host: str = YELP_API_HOST,
    bearer_token: Optional[YelpAccessToken] = None,
    query_params: Optional[Dict[str, str]] = None,
    payload: Optional[Dict[str, str]] = None,
    extra_headers: Optional[Dict[str, str]] = None,
) -> YelpApiResponse:
    """
    Function to make requests to Yelp APIs.

    Args:
        http_method: HTTP method (GET, POST)
        api_function: API endpoint to call (e.g., "/v3/bookings/{business_id}/openings")
        api_host: API host to use (default: YELP_API_HOST)
        bearer_token: Yelp bearer token for authentication
        query_params: Query parameters to include in the request
        payload: Body data for POST requests
        extra_headers: Additional headers to include in the request

    Returns:
        YelpApiResponse object containing the response data

    Raises:
        Exception: If the API request fails
    """
    logger.debug(
        f"[YelpTool._apis._utils.connect_yelp_api] Calling Yelp API: {http_method} {api_function} | "
        f"Query Params: {query_params} | "
        f"Extra Headers: {extra_headers} | "
        f"Payload: {payload}"
    )

    headers = {"Accept": "application/json"}

    if bearer_token:
        headers["Authorization"] = bearer_token.get_token_header_value()

    if extra_headers:
        headers.update(extra_headers)

    request_body = ""
    if payload:
        content_type = headers.get("Content-Type", "")
        if "application/x-www-form-urlencoded" in content_type:
            request_body = urlencode(payload)
        else:
            headers["Content-Type"] = "application/json"
            request_body = json.dumps(payload)

    if query_params:
        api_function += "?" + urlencode(query_params)

    try:
        conn = http.client.HTTPSConnection(api_host, timeout=30)
        conn.request(http_method, api_function, request_body, headers=headers)

        response = conn.getresponse()
        response_data = response.read().decode("utf-8")

        decoded_body = {}
        if response_data and response.getheader("Content-Type", "").startswith(
            "application/json"
        ):
            try:
                decoded_body = json.loads(response_data)
            except json.JSONDecodeError:
                logger.debug(f"Failed to decode JSON response: {response_data[:200]}")
                decoded_body = {"raw_content": response_data}
        elif response_data:
            decoded_body = {"raw_content": response_data}

        yelp_response = YelpApiResponse(
            status=response.status, reason=response.reason, decoded_body=decoded_body
        )

        logger.debug(
            f"[YelpTool._apis._utils.connect_yelp_api] {http_method} {api_function} -> {yelp_response.status} - {yelp_response.reason}"
        )

        return yelp_response

    except Exception as e:
        raise Exception(
            f"[YelpTool._apis._utils.connect_yelp_api] Error while calling {http_method} {api_function}: {str(e)}"
        ) from e
    finally:
        conn_var = locals().get("conn")
        if conn_var:
            conn_var.close()
