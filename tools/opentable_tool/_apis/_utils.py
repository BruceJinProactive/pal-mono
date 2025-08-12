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

DEFAULT_TIMEOUT = 30  # 30 seconds default timeout


def connect_opentable_api(
    http_method: HttpMethod,
    bearer_token: OpenTableAccessToken,
    api_function: str,
    query_params: Optional[Dict[str, str]] = None,
    extra_headers: Optional[Dict[str, str]] = None,
    payload: Optional[dict] = None,
    timeout: int = DEFAULT_TIMEOUT,
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

    Returns:
        OpenTableResponse object containing the response data
    """
    host = "www.opentable.com"

    # Log the request details
    logger.info(f"[OpenTable API] Starting request to {host}{api_function}")
    logger.info(f"[OpenTable API] Method: {http_method.value}")
    logger.info(f"[OpenTable API] Timeout: {timeout}s")
    logger.info(f"[OpenTable API] Bearer token: {bearer_token.access_token[:20]}...")

    if query_params:
        logger.info(f"[OpenTable API] Query params: {query_params}")
    if payload:
        logger.info(f"[OpenTable API] Payload: {payload}")
    if extra_headers:
        logger.info(f"[OpenTable API] Extra headers: {extra_headers}")

    # Build the query string if query parameters are provided
    query_string = ""
    if query_params:
        query_string = f"?{urlencode(query_params)}"

    logger.info(f"[OpenTable API] Final URL: {host}{api_function}{query_string}")

    # Set up the connection with timeout
    logger.info(
        f"[OpenTable API] Setting up connection to {host} with timeout {timeout}s"
    )
    conn = http.client.HTTPSConnection(host, timeout=timeout)
    logger.info("[OpenTable API] Connection established successfully")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {bearer_token.access_token}",
    }

    # Add extra headers if provided
    if extra_headers:
        headers.update(extra_headers)

    logger.info(f"[OpenTable API] Headers: {headers}")

    # Convert payload to JSON if provided
    json_payload = None
    if payload:
        json_payload = json.dumps(payload)

    logger.info(f"[OpenTable API] JSON payload: {json_payload}")

    try:
        # Make the request
        logger.info(
            f"[OpenTable API] Making {http_method.value} request to {host}{api_function}{query_string}"
        )
        conn.request(
            method=http_method.value,
            url=f"{api_function}{query_string}",
            body=json_payload,
            headers=headers,
        )

        # Get the response
        logger.info("[OpenTable API] Waiting for response")
        response = conn.getresponse()
        status = response.status
        reason = response.reason

        # Read and decode the response body
        logger.info("[OpenTable API] Reading response body")
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

        logger.info("[OpenTable API] Response completed successfully")

        return OpenTableResponse(
            status=status, reason=reason, decoded_body=decoded_body
        )

    except Exception as e:
        logger.error(f"Error connecting to OpenTable API: {str(e)}")
        return OpenTableResponse(status=500, reason=str(e), decoded_body={})
    finally:
        conn.close()
