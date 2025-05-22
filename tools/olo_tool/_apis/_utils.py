import http.client
import json
import urllib.parse
from typing import Type, TypeVar, Union

from tools.olo_tool.classes import HttpMethod, OloAccessToken, OloHubResponse
from utils.log import logger

BASE_URL = "ordering.api.olosandbox.com"

T = TypeVar("T")


def handle_olo_response(
    response: OloHubResponse, response_type: Type[T] | None = None
) -> Union[T, str]:
    """
    Handle Olo API response and convert to appropriate type.

    Args:
        response: The OloHubResponse object
        response_type: Optional type to validate and convert the response to

    Returns:
        The converted response object or raw response string if no type specified

    Raises:
        ValueError: If the response status is not 200 or validation fails
    """
    if response.status != 200:
        error_msg = (
            f"API call failed with status {response.status}: {response.decoded_body}"
        )
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


def connect_olo_order_hub(
    http_method: HttpMethod,
    bearer_token: OloAccessToken,
    api_function: str,
    query_params: dict | None = None,
    extra_headers: dict | None = None,
    payload: dict | str | None = None,
) -> OloHubResponse:
    """
    Make a request to the Olo Order Hub API.

    Args:
        http_method: The HTTP method to use
        bearer_token: The Olo access token
        api_function: The API endpoint to call
        query_params: Optional query parameters
        extra_headers: Optional additional headers
        payload: Optional request payload

    Returns:
        OloHubResponse: The API response

    Raises:
        ValueError: If the HTTP method is invalid or the request fails
    """
    logger.debug(
        f"[OloTool._apis._utils.connect_olo_order_hub] Calling Olo API: {http_method} {api_function} | "
        f"Query Params: {query_params} | "
        f"Extra Headers: {extra_headers} | "
        f"Payload: {payload}"
    )

    # Set up headers
    headers = {
        "Content-Type": "application/json",
        "Authorization": bearer_token.get_token_header_value(),
    }

    # Add any extra headers
    if extra_headers:
        headers.update(extra_headers)

    # Prepare payload
    request_body = ""
    if payload is not None:
        if isinstance(payload, dict):
            request_body = json.dumps(payload)
        else:
            request_body = payload

    # Construct the full URL with query parameters
    if query_params:
        api_function += "?" + urllib.parse.urlencode(query_params)

    try:
        conn = http.client.HTTPSConnection(BASE_URL, timeout=30)
        if http_method in [HttpMethod.GET, HttpMethod.POST, HttpMethod.PUT]:
            conn.request(http_method.value, api_function, request_body, headers=headers)
        else:
            raise ValueError(
                f"[OloTool._apis._utils.connect_olo_order_hub] Invalid HTTP method: {http_method}"
            )

        response = conn.getresponse()
        response_data = response.read().decode("utf-8")

        # If response status is not 200, raise an exception
        if response.status != 200:
            raise Exception(
                f"Error: {response.status} - {response.reason} - {response_data}"
            )

        olo_response = OloHubResponse(
            status=response.status,
            reason=response.reason,
            decoded_body=response_data,
        )
        logger.debug(
            f"[OloTool._apis._utils.connect_olo_order_hub] OloResponse: {olo_response}"
        )
        return olo_response

    except Exception as e:
        raise Exception(
            f"[OloTool._apis._utils.connect_olo_order_hub] Error while calling {http_method} {api_function}: {str(e)}"
        ) from e
    finally:
        conn_var = locals().get("conn")
        if conn_var:
            conn_var.close()
