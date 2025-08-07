import http.client
import json
from typing import Dict, Optional
from urllib.parse import urlencode

from tools.opentable_tool.classes import (
    HttpMethod,
    OpenTableAccessToken,
    OpenTableResponse,
)
from utils.log import logger

# Production and pre-production API hosts
PRODUCTION_HOST = "api.opentable.com"
PREPROD_HOST = "api-pp.opentable.com"
DEFAULT_TIMEOUT = 30  # 30 seconds default timeout


def connect_opentable_api(
    http_method: HttpMethod,
    bearer_token: OpenTableAccessToken,
    api_function: str,
    query_params: Optional[Dict[str, str]] = None,
    extra_headers: Optional[Dict[str, str]] = None,
    payload: Optional[dict] = None,
    timeout: int = DEFAULT_TIMEOUT,
    use_production: bool = False,
) -> OpenTableResponse:
    """
    Makes a request to the OpenTable API.

    Args:
        http_method: HTTP method to use (GET, POST, PUT, DELETE)
        bearer_token: OpenTable access token
        api_function: API endpoint to call
        query_params: Query parameters to include in the request
        extra_headers: Additional headers to include in the request
        payload: JSON payload to include in the request
        timeout: Connection and read timeout in seconds (default: 30)
        use_production: Whether to use production (True) or pre-production (False) environment

    Returns:
        OpenTableResponse object containing the response data
    """
    # Determine the appropriate host based on the endpoint
    if api_function.startswith("/restref/"):
        # Use the main OpenTable domain for restref endpoints
        host = "www.opentable.com"
    else:
        # Use API subdomain for other endpoints
        host = PRODUCTION_HOST if use_production else PREPROD_HOST

    # Build the query string if query parameters are provided
    query_string = ""
    if query_params:
        query_string = f"?{urlencode(query_params)}"

    # Set up the connection with timeout
    conn = http.client.HTTPSConnection(host, timeout=timeout)

    # Set up headers to match Postman
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {bearer_token.access_token}",
        "User-Agent": "PostmanRuntime/7.45.0",
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }

    # Add cookies for restref endpoints
    if api_function.startswith("/restref/"):
        headers["Cookie"] = "OT-Locale=en-US"

    # Add extra headers if provided
    if extra_headers:
        headers.update(extra_headers)

    # Convert payload to JSON if provided
    json_payload = None
    if payload:
        json_payload = json.dumps(payload)

    try:
        # Make the request
        conn.request(
            method=http_method.value,
            url=f"{api_function}{query_string}",
            body=json_payload,
            headers=headers,
        )

        # Get the response
        response = conn.getresponse()
        status = response.status
        reason = response.reason

        # Read and decode the response body
        response_data = response.read().decode("utf-8")

        # Parse the response if it's JSON
        decoded_body = {}  # Default to empty dict
        if response_data and response.getheader("Content-Type", "").startswith(
            "application/json"
        ):
            try:
                decoded_body = json.loads(response_data)
            except json.JSONDecodeError:
                logger.error(f"Failed to decode JSON response: {response_data}")
                # Keep the empty dict as decoded_body
        elif response_data:
            # For non-JSON responses, store the raw data in a structured way
            decoded_body = {"raw_content": response_data}

        return OpenTableResponse(
            status=status, reason=reason, decoded_body=decoded_body
        )

    except Exception as e:
        logger.error(f"Error connecting to OpenTable API: {str(e)}")
        return OpenTableResponse(status=500, reason=str(e), decoded_body={})
    finally:
        conn.close()
