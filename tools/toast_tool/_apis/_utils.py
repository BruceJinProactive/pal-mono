from tools.toast_tool.classes import ToastAccessToken
from tools.utils.ordering._utils import connect_order_hub
from tools.utils.ordering.classes import ApiProvider, GenericHubResponse, HttpMethod


def connect_toast_order_hub(
    http_method: HttpMethod,
    bearer_token: ToastAccessToken,
    api_function: str,
    store_id: str,
    query_params: dict | None = None,
    extra_headers: dict | None = None,
    payload: dict | str | None = None,
    general_api_endpoint: str | None = None,
) -> GenericHubResponse:
    """
    Make a request to the Toast Order Hub API using the generic connect function.

    Args:
        http_method: The HTTP method to use
        bearer_token: The Toast access token
        api_function: The API endpoint to call
        store_id: The store ID (required for Toast API)
        query_params: Optional query parameters
        extra_headers: Optional additional headers
        payload: Optional request payload
        general_api_endpoint: Optional custom API endpoint

    Returns:
        GenericHubResponse: The API response

    Raises:
        ValueError: If the HTTP method is invalid or the request fails
    """
    return connect_order_hub(
        provider=ApiProvider.TOAST,
        http_method=http_method,
        bearer_token=bearer_token,
        api_function=api_function,
        query_params=query_params,
        extra_headers=extra_headers,
        payload=payload,
        store_id=store_id,
        general_api_endpoint=general_api_endpoint,
    )
