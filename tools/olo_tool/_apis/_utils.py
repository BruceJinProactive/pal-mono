from typing import Type, TypeVar, Union

from tools.olo_tool.classes import OloAccessToken
from utils.log import logger
from utils.ordering._utils import connect_order_hub
from utils.ordering.classes import ApiProvider, GenericHubResponse, HttpMethod

T = TypeVar("T")


def handle_olo_response(
    response: GenericHubResponse, response_type: Type[T] | None = None
) -> Union[T, str]:
    """
    Handle Olo API response and convert to appropriate type.

    Args:
        response: The GenericHubResponse object
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
) -> GenericHubResponse:
    """
    Make a request to the Olo Order Hub API using the generic connect function.

    Args:
        http_method: The HTTP method to use
        bearer_token: The Olo access token
        api_function: The API endpoint to call
        query_params: Optional query parameters
        extra_headers: Optional additional headers
        payload: Optional request payload

    Returns:
        GenericHubResponse: The API response

    Raises:
        ValueError: If the HTTP method is invalid or the request fails
    """
    return connect_order_hub(
        provider=ApiProvider.OLO,
        http_method=http_method,
        bearer_token=bearer_token,
        api_function=api_function,
        query_params=query_params,
        extra_headers=extra_headers,
        payload=payload,
    )
