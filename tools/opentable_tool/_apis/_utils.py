import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, Optional

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
    Makes a request to the OpenTable API using urllib.

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
    base_url = f"https://{host}{api_function}"

    # Log the request details
    logger.info(f"[OpenTable API] Starting request to {base_url}")
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
    if query_params:
        query_string = "&".join(
            [f"{k}={urllib.parse.quote(str(v))}" for k, v in query_params.items()]
        )
        if not api_function.startswith("?"):
            base_url += "?"
        base_url += query_string

    logger.info(f"[OpenTable API] Final URL: {base_url}")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {bearer_token.access_token}",
    }

    # Add extra headers if provided
    if extra_headers:
        headers.update(extra_headers)

    logger.info(f"[OpenTable API] Headers: {headers}")

    # Prepare request data
    request_data = None

    if payload:
        try:
            request_data = json.dumps(payload).encode("utf-8")
            logger.info(f"[OpenTable API] JSON payload: {payload}")
        except Exception as e:
            logger.error(f"[OpenTable API] Failed to serialize payload: {str(e)}")
            return OpenTableResponse(
                status=500,
                reason=f"Payload serialization failed: {str(e)}",
                decoded_body={},
            )

    try:
        # Create and send the request
        logger.info(f"[OpenTable API] Making {http_method.value} request...")

        request = urllib.request.Request(
            url=base_url, data=request_data, headers=headers, method=http_method.value
        )

        logger.info("[OpenTable API] Request created, sending...")

        # Send the request and get response
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.status
            reason = response.reason

            logger.info(f"[OpenTable API] Response received: {status} {reason}")
            logger.info(
                f"[OpenTable API] Response headers: {dict(response.getheaders())}"
            )

            # Read and decode the response body
            logger.info("[OpenTable API] Reading response body...")
            response_data = response.read().decode("utf-8")
            logger.info(
                f"[OpenTable API] Response body length: {len(response_data)} characters"
            )
            logger.info(
                f"[OpenTable API] Response body preview: {response_data[:200]}..."
            )

            # Parse the response if it's JSON
            decoded_body = {}  # Default to empty dict
            content_type = response.getheader("Content-Type", "")

            if response_data and content_type.startswith("application/json"):
                try:
                    decoded_body = json.loads(response_data)
                    logger.info("[OpenTable API] Successfully parsed JSON response")
                except json.JSONDecodeError as e:
                    logger.error(f"[OpenTable API] Failed to decode JSON response: {e}")
                    logger.error(f"[OpenTable API] Raw response: {response_data}")
                    decoded_body = {"raw_content": response_data, "parse_error": str(e)}
            elif response_data:
                # For non-JSON responses, store the raw data in a structured way
                decoded_body = {"raw_content": response_data}
                logger.info("[OpenTable API] Stored raw response content")

            logger.info("[OpenTable API] Request completed successfully")
            return OpenTableResponse(
                status=status, reason=reason, decoded_body=decoded_body
            )

    except urllib.error.HTTPError as e:
        logger.error(f"[OpenTable API] HTTP Error: {e.code} {e.reason}")
        # Try to read the error response body
        try:
            error_body = e.read().decode("utf-8")
            logger.error(f"[OpenTable API] Error response body: {error_body}")
            decoded_body = {"error": str(e), "response_body": error_body}
        except Exception:
            decoded_body = {"error": str(e)}

        return OpenTableResponse(
            status=e.code, reason=e.reason, decoded_body=decoded_body
        )
    except urllib.error.URLError as e:
        logger.error(f"[OpenTable API] URL Error: {str(e)}")
        return OpenTableResponse(
            status=500, reason=f"URL Error: {str(e)}", decoded_body={"error": str(e)}
        )
    except Exception as e:
        logger.error(f"[OpenTable API] Unexpected error: {str(e)}", exc_info=True)
        return OpenTableResponse(
            status=500,
            reason=f"Unexpected error: {str(e)}",
            decoded_body={"error": str(e)},
        )
