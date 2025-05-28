import http.client
import json
from enum import Enum
from typing import Dict, Optional
from urllib.parse import urlencode

from tools.yelp_tool.classes import YelpApiResponse
from utils.log import logger

# Yelp API configuration
YELP_API_HOST = "api.yelp.com"
YELP_PARTNER_API_HOST = "partner-api.yelp.com"
DEFAULT_TIMEOUT = 30  # 30 seconds default timeout


class RequestType(Enum):
    """Enum for different types of API requests"""

    GET = "GET"
    POST = "POST"


class ApiHost(Enum):
    """Enum for different API hosts"""

    YELP_API = YELP_API_HOST
    YELP_PARTNER_API = YELP_PARTNER_API_HOST


def connect_yelp_api(
    api_function: str,
    request_type: RequestType,
    api_host: ApiHost = ApiHost.YELP_API,
    api_key: Optional[str] = None,
    query_params: Optional[Dict[str, str]] = None,
    body_data: Optional[Dict[str, str]] = None,
    extra_headers: Optional[Dict[str, str]] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> YelpApiResponse:
    """
    Function to make requests to Yelp APIs.

    Args:
        api_function: API endpoint to call (e.g., "/v3/bookings/{business_id}/openings")
        request_type: Type of request (GET or POST)
        api_host: Which API host to use (YELP_API or YELP_PARTNER_API)
        api_key: Yelp API key for authentication (required for YELP_API, optional for YELP_PARTNER_API)
        query_params: Query parameters to include in the request (for GET requests)
        body_data: Body data for POST requests
        extra_headers: Additional headers to include in the request (use Content-Type to specify form vs JSON)
        timeout: Connection and read timeout in seconds (default: 30)

    Returns:
        YelpApiResponse object containing the response data

    Raises:
        ValueError: If required parameters are missing or invalid
        Exception: If the API request fails
    """
    # Validate inputs
    if request_type == RequestType.GET and body_data is not None:
        raise ValueError("GET requests cannot have body data")

    if request_type == RequestType.POST and body_data is None:
        raise ValueError("POST requests require body data")

    if api_host == ApiHost.YELP_API and api_key is None:
        raise ValueError("API key is required for Yelp API requests")

    # Build URL
    url = api_function
    if request_type == RequestType.GET and query_params:
        url += f"?{urlencode(query_params)}"

    # Set up base headers
    headers = {"Accept": "application/json"}

    # Add authentication for Yelp API
    if api_host == ApiHost.YELP_API and api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # Set content type and prepare body for POST requests
    request_body = None
    if request_type == RequestType.POST:
        # Auto-detect content type from extra_headers or default to JSON
        content_type = "application/json"  # Default
        if extra_headers and "Content-Type" in extra_headers:
            content_type = extra_headers["Content-Type"]
        elif extra_headers and "content-type" in extra_headers:
            content_type = extra_headers["content-type"]

        headers["Content-Type"] = content_type

        # Encode body based on content type
        if "application/x-www-form-urlencoded" in content_type:
            request_body = urlencode(body_data) if body_data else ""
        else:
            # Default to JSON encoding
            request_body = json.dumps(body_data)

    # Add extra headers if provided
    if extra_headers:
        headers.update(extra_headers)

    # Determine HTTP method
    http_method = "GET" if request_type == RequestType.GET else "POST"

    try:
        # Set up the connection with timeout
        conn = http.client.HTTPSConnection(api_host.value, timeout=timeout)

        # Make the request
        conn.request(
            method=http_method,
            url=url,
            body=request_body,
            headers=headers,
        )

        # Get the response
        response = conn.getresponse()
        response_data = response.read().decode("utf-8")

        # Parse the response if it's JSON
        decoded_body = {}  # Default to empty dict
        if response_data and response.getheader("Content-Type", "").startswith(
            "application/json"
        ):
            try:
                decoded_body = json.loads(response_data)
            except json.JSONDecodeError:
                logger.debug(f"Failed to decode JSON response: {response_data[:200]}")
                # Keep the empty dict as decoded_body
        elif response_data:
            # For non-JSON responses, store the raw data in a structured way
            decoded_body = {"raw_content": response_data}

        yelp_response = YelpApiResponse(
            status=response.status, reason=response.reason, decoded_body=decoded_body
        )

        logger.debug(
            f"[YelpTool._apis._utils.connect_yelp_api] {http_method} {api_function} -> {yelp_response.status} - {yelp_response.reason}"
        )

        return yelp_response

    except http.client.HTTPException as e:
        raise Exception(
            f"[YelpTool._apis._utils.connect_yelp_api] HTTP protocol error while calling {http_method} {api_function}: Invalid HTTP communication. Original error: {str(e)}"
        ) from e

    except UnicodeDecodeError as e:
        raise Exception(
            f"[YelpTool._apis._utils.connect_yelp_api] Response decoding error while calling {http_method} {api_function}: Unable to decode response as UTF-8. Original error: {str(e)}"
        ) from e

    except ValueError as e:
        raise Exception(
            f"[YelpTool._apis._utils.connect_yelp_api] Invalid parameter error while calling {http_method} {api_function}: Invalid URL or parameter format. Original error: {str(e)}"
        ) from e

    except Exception as e:
        raise Exception(
            f"[YelpTool._apis._utils.connect_yelp_api] Unexpected error while calling {http_method} {api_function}: {str(e)}"
        ) from e
    finally:
        conn_var = locals().get("conn")
        if conn_var:
            conn_var.close()
