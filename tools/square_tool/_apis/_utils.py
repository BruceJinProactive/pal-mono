import http.client
import json
from typing import Type, TypeVar, Union

from tools.square_tool.classes import SquareAccessToken
from tools.utils.ordering.classes import GenericHubResponse, HttpMethod
from utils.log import logger

T = TypeVar("T")


def handle_square_response(
    response: GenericHubResponse, response_type: Type[T] | None = None
) -> Union[T, str]:
    """
    Handle Square API response and convert to appropriate type.

    Args:
        response: The GenericHubResponse object
        response_type: Optional type to validate and convert the response to

    Returns:
        The converted response object or raw response string if no type specified

    Raises:
        ValueError: If the response status is not 200 or validation fails
    """
    if response.status != 200:
        error_msg = f"Square API call failed with status {response.status}: {response.decoded_body}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    if response_type:
        try:
            return response_type.model_validate_json(response.decoded_body)  # type: ignore
        except Exception as e:
            error_msg = (
                f"Failed to validate response as {response_type.__name__}: {str(e)}"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

    return response.decoded_body


def connect_square_api(
    http_method: HttpMethod,
    access_token: SquareAccessToken,
    api_function: str,
    query_params: dict | None = None,
    extra_headers: dict | None = None,
    payload: dict | str | None = None,
    use_production: bool = False,
    square_version: str = "2025-05-21",
) -> GenericHubResponse:
    """
    Make a request to the Square API.

    Args:
        http_method: The HTTP method to use (GET, POST, PUT, DELETE)
        access_token: The Square access token model containing the token and type
        api_function: The API endpoint to call (e.g., "/v2/catalog/search")
        query_params: Optional query parameters
        extra_headers: Optional additional headers
        payload: Optional request payload
        use_production: Whether to use production (True) or sandbox (False) environment
        square_version: Square API version (defaults to 2025-05-21)

    Returns:
        GenericHubResponse: The API response

    Raises:
        ValueError: If the HTTP method is invalid or the request fails
    """
    # Determine base URL
    base_url = (
        "connect.squareup.com" if use_production else "connect.squareupsandbox.com"
    )

    # Build headers
    headers = {
        "Square-Version": square_version,
        "Authorization": f"{access_token.token_type} {access_token.access_token}",
        "Content-Type": "application/json",
    }

    # Add extra headers if provided
    if extra_headers:
        headers.update(extra_headers)

    # Prepare the path
    path = api_function

    # Add query parameters if provided
    if query_params:
        from urllib.parse import urlencode

        query_string = urlencode(query_params)
        path = f"{path}?{query_string}"

    # Prepare request body
    body = ""
    if payload:
        if isinstance(payload, dict):
            body = json.dumps(payload)
        else:
            body = payload

    # Validate HTTP method
    method_str = (
        http_method.value
        if isinstance(http_method, HttpMethod)
        else str(http_method).upper()
    )
    valid_methods = ["GET", "POST", "PUT", "DELETE"]
    if method_str not in valid_methods:
        raise ValueError(
            f"Invalid HTTP method: {method_str}. Must be one of {valid_methods}"
        )

    try:
        # Create connection
        conn = http.client.HTTPSConnection(base_url)

        try:
            # Make request
            conn.request(method_str, path, body, headers)

            # Get response
            response = conn.getresponse()

            # Return standardized response
            return GenericHubResponse(
                status=response.status,
                reason=response.reason,
                decoded_body=response.read().decode("utf-8"),
            )
        finally:
            # Ensure connection is always closed
            conn.close()

    except Exception as e:
        error_msg = f"Failed to connect to Square API: {str(e)}"
        logger.error(error_msg)
        raise ValueError(error_msg)
