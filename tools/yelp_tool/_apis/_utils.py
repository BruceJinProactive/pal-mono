import http.client
import json
from typing import Dict, Optional
from urllib.parse import urlencode

from tools.yelp_tool.classes import YelpApiResponse
from utils.log import logger

# Yelp API configuration
YELP_API_HOST = "api.yelp.com"
YELP_PARTNER_API_HOST = "partner-api.yelp.com"
DEFAULT_TIMEOUT = 30  # 30 seconds default timeout


def connect_yelp_api(
    api_key: str,
    api_function: str,
    query_params: Optional[Dict[str, str]] = None,
    extra_headers: Optional[Dict[str, str]] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> YelpApiResponse:
    """
    Makes a GET request to the Yelp API.

    Args:
        api_key: Yelp API key for authentication
        api_function: API endpoint to call (e.g., "/v3/bookings/{business_id}/openings")
        query_params: Query parameters to include in the request
        extra_headers: Additional headers to include in the request
        timeout: Connection and read timeout in seconds (default: 30)

    Returns:
        YelpApiResponse object containing the response data
    """
    # Build the query string if query parameters are provided
    query_string = ""
    if query_params:
        query_string = f"?{urlencode(query_params)}"

    # Set up headers
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }

    # Add extra headers if provided
    if extra_headers:
        headers.update(extra_headers)

    try:
        # Set up the connection with timeout
        conn = http.client.HTTPSConnection(YELP_API_HOST, timeout=timeout)

        # Make the GET request
        conn.request(
            method="GET",
            url=f"{api_function}{query_string}",
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
            f"[YelpTool._apis._utils.connect_yelp_api] YelpResponse: {yelp_response.status} - {yelp_response.reason}"
        )

        return yelp_response

    except http.client.HTTPException as e:
        raise Exception(
            f"[YelpTool._apis._utils.connect_yelp_api] HTTP protocol error while calling GET {api_function}: Invalid HTTP communication"
        ) from e

    except UnicodeDecodeError as e:
        raise Exception(
            f"[YelpTool._apis._utils.connect_yelp_api] Response decoding error while calling GET {api_function}: Unable to decode response as UTF-8"
        ) from e

    except ValueError as e:
        raise Exception(
            f"[YelpTool._apis._utils.connect_yelp_api] Invalid parameter error while calling GET {api_function}: Invalid URL or parameter format"
        ) from e

    except Exception as e:
        raise Exception(
            f"[YelpTool._apis._utils.connect_yelp_api] Unexpected error while calling GET {api_function}: {str(e)}"
        ) from e
    finally:
        conn_var = locals().get("conn")
        if conn_var:
            conn_var.close()


def connect_yelp_partner_api_post(
    api_function: str,
    body_data: Dict,
    extra_headers: Optional[Dict[str, str]] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> YelpApiResponse:
    """
    Makes a POST request to the Yelp Partner API.

    Args:
        api_function: API endpoint to call (e.g., "/token/v1")
        body_data: Dictionary containing the request body data
        extra_headers: Additional headers to include in the request
        timeout: Connection and read timeout in seconds (default: 30)

    Returns:
        YelpApiResponse object containing the response data
    """
    # Set up headers
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    # Add extra headers if provided
    if extra_headers:
        headers.update(extra_headers)

    # Convert body data to JSON
    json_body = json.dumps(body_data)

    try:
        # Set up the connection with timeout
        conn = http.client.HTTPSConnection(YELP_PARTNER_API_HOST, timeout=timeout)

        # Make the POST request
        conn.request(
            method="POST",
            url=api_function,
            body=json_body,
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
                logger.debug(f"Failed to decode JSON response: {response_data}")
                # Keep the empty dict as decoded_body
        elif response_data:
            # For non-JSON responses, store the raw data in a structured way
            decoded_body = {"raw_content": response_data}

        yelp_response = YelpApiResponse(
            status=response.status, reason=response.reason, decoded_body=decoded_body
        )

        logger.debug(
            f"[YelpTool._apis._utils.connect_yelp_partner_api_post] YelpResponse: {yelp_response.status} - {yelp_response.reason}"
        )

        return yelp_response

    except http.client.HTTPException as e:
        raise Exception(
            f"[YelpTool._apis._utils.connect_yelp_partner_api_post] HTTP protocol error while calling POST {api_function}: Invalid HTTP communication"
        ) from e

    except UnicodeDecodeError as e:
        raise Exception(
            f"[YelpTool._apis._utils.connect_yelp_partner_api_post] Response decoding error while calling POST {api_function}: Unable to decode response as UTF-8"
        ) from e

    except ValueError as e:
        raise Exception(
            f"[YelpTool._apis._utils.connect_yelp_partner_api_post] Invalid parameter error while calling POST {api_function}: Invalid URL or parameter format"
        ) from e

    except Exception as e:
        raise Exception(
            f"[YelpTool._apis._utils.connect_yelp_partner_api_post] Unexpected error while calling POST {api_function}: {str(e)}"
        ) from e
    finally:
        conn_var = locals().get("conn")
        if conn_var:
            conn_var.close()
