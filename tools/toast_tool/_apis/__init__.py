import http.client
import json
from typing import Optional

from tools.toast_tool._apis._utils import API_TIMEOUT
from tools.toast_tool.classes import (
    HttpMethod,
    Order,
    RestaurantInfo,
    RestaurantOrderingStatus,
    ToastAccessToken,
)
from utils.log import logger

from . import _utils


def get_toast_access_token(
    client_id: str,
    client_secret: str,
    logging_enabled: bool = True,
) -> Optional[ToastAccessToken]:
    """
    Obtains an access token from the Toast Authentication API.

    Args:
        client_id: Your Toast API client identifier
        client_secret: Your Toast API client secret
        logging_enabled: Whether to log the authentication process

    Returns:
        `ToastAccessToken` object if successful, None otherwise
    """
    # Define constants for the API request
    TOAST_API_HOST_NAME = "toast-api-server"
    USER_ACCESS_TYPE = "TOAST_MACHINE_CLIENT"

    payload = {
        "clientId": client_id,
        "clientSecret": client_secret,
        "userAccessType": USER_ACCESS_TYPE,
    }

    headers = {"Content-Type": "application/json"}

    if logging_enabled:
        logger.info("[ToastAPI.get_toast_access_token] Authenticating with Toast API")
        logger.info(
            f"[ToastAPI.get_toast_access_token] Using client ID: {'*' * 8}{client_id[-4:] if len(client_id) > 4 else '*' * 4}"
        )
    try:
        conn = http.client.HTTPSConnection(TOAST_API_HOST_NAME, timeout=API_TIMEOUT)
        conn.request(
            "POST",
            "/authentication/v1/authentication/login",
            json.dumps(payload),
            headers,
        )

        # Get the response from the server
        response = conn.getresponse()
        response_data = response.read().decode("utf-8")

        # If successful, parse the response
        # and create a ToastAccessToken object
        if response.status == 200:
            response_data = json.loads(response_data)

            # The response_data variable should contain a `status` field and a `token` field

            token = ToastAccessToken.from_toast_response(response_data=response_data)

            # Check if the token is valid
            if not token.is_valid():
                raise ValueError(
                    "[ToastAPI.get_toast_access_token] Failed to authenticate with Toast API. Invalid token"
                )

            if logging_enabled:
                logger.info(
                    "[ToastAPI.get_toast_access_token] Successfully authenticated with Toast API"
                )
                logger.info(
                    f"[ToastAPI.get_toast_access_token] Token expires in: {token.expires_in} seconds"
                )
            return token
        else:
            raise ValueError(
                f"[ToastAPI.get_toast_access_token] Failed to authenticate with Toast API. Status code: {response.status}"
            )
    except Exception as e:
        logger.error(f"[ToastAPI.get_toast_access_token] An error occurred: {e}")
    finally:
        # Ensure the connection is closed after use
        if "conn" in locals():
            conn.close()  # type: ignore


def get_store_info(
    bearer_token: ToastAccessToken,
    store_id: str,
    include_archived: bool = False,
) -> RestaurantInfo:
    """
    Get restaurant information from the Toast API.

    Args:
        bearer_token: Toast access token
        store_id: External ID for the restaurant
        include_archived: Whether to include archived restaurants

    Returns:
        RestaurantInfo object or None if request failed
    """
    query_params = {"includeArchived": str(include_archived).lower()}
    try:
        response = _utils.connect_toast_order_hub(
            http_method=HttpMethod.GET,
            bearer_token=bearer_token,
            api_function=f"restaurants/v1/restaurants/{store_id}",
            store_id=store_id,
            query_params=query_params,
            extra_headers=None,
            payload=None,
            logging_enabled=True,
        )
    except Exception as e:
        # Will handle the exception at LLM level
        raise Exception(
            f"[ToastAPI.get_store_info] Error while calling Toast API: {str(e)}"
        ) from e

    if response.status == 200:
        # Convert the JSON string to a RestaurantInfo object
        restaurant_info = RestaurantInfo.model_validate_json(response.decoded_body)

        return restaurant_info
    else:
        logger.error(
            f"[ToastAPI.get_store_info] Failed to get restaurant info with status {response.status}: {response.decoded_body}"
        )
        raise ValueError(
            f"Failed to get restaurant info with status {response.status}: {response.decoded_body}"
        )


def get_online_ordering_status(
    bearer_token: ToastAccessToken,
    store_id: str,
    logging_enabled: bool = True,
) -> RestaurantOrderingStatus:
    """
    Get the online ordering availability status for a Toast restaurant.

    Args:
        bearer_token: Toast access token
        store_id: External ID for the restaurant
        logging_enabled: Whether to log request and response details

    Returns:
        RestaurantOrderingStatus object containing the availability status
        or raises an exception if the request fails.
    """
    try:
        response = _utils.connect_toast_order_hub(
            http_method=HttpMethod.GET,
            bearer_token=bearer_token,
            api_function="restaurant-availability/v1/availability",
            store_id=store_id,
            query_params=None,
            extra_headers=None,
            payload=None,
            logging_enabled=logging_enabled,
        )
    except Exception as e:
        raise Exception(
            f"[ToastAPI.get_online_ordering_status] Error while calling Toast API: {str(e)}"
        ) from e

    if response.status == 200:
        availability_info = RestaurantOrderingStatus.model_validate_json(
            response.decoded_body
        )
        return availability_info
    else:
        logger.error(
            f"Failed to get online ordering status with status {response.status}: {response.decoded_body}"
        )
        raise ValueError(
            f"Failed to get online ordering status with status {response.status}: {response.decoded_body}"
        )


def get_order_prices(
    bearer_token: ToastAccessToken,
    store_id: str,
    order_data: Order,
) -> Order:
    """
    Calculates the check price amounts, tax amounts, and service charges for an Order object.

    Args:
        bearer_token: Toast access token
        store_id: External ID for the restaurant
        order_data: Order object containing the order details

    Returns:
        `Order` object with the base price, tax amount, and total price of each `check` object. The returned `Order` object will be used to submit the order to the Toast API.
    """
    # Make the API call to the order prices endpoint
    try:
        response = _utils.connect_toast_order_hub(
            http_method=HttpMethod.POST,
            bearer_token=bearer_token,
            api_function="orders/v2/prices",
            store_id=store_id,
            query_params=None,
            extra_headers={"Content-Type": "application/json"},
            payload=order_data.model_dump(),
            logging_enabled=True,
        )
    except Exception as e:
        raise Exception(
            f"[ToastAPI.get_order_prices] Error while calling Toast API: {str(e)}"
        ) from e

    # Process the response
    if response.status == 200:
        # Convert the JSON string to an Order object
        order_prices = Order.model_validate_json(response.decoded_body)
        return order_prices
    else:
        logger.error(
            f"Order price calculation failed with status {response.status}: {response.decoded_body}"
        )
        raise ValueError(
            f"Order price calculation failed with status {response.status}: {response.decoded_body}"
        )


def submit_order(bearer_token: ToastAccessToken, store_id: str, order: Order) -> Order:
    """
    Submits an order to the Toast API.

    Args:
        bearer_token (ToastAccessToken): The Toast access token.
        store_id (str): The external ID of the restaurant.
        order (Order): The Order object to be submitted.

    Returns:
        `Order` object that has been persisted in Toast.
    """
    try:
        response = _utils.connect_toast_order_hub(
            http_method=HttpMethod.POST,
            bearer_token=bearer_token,
            api_function="orders/v2/orders",
            store_id=store_id,
            payload=order.model_dump(),
            logging_enabled=True,
        )
    except Exception as e:
        raise Exception(
            f"[ToastAPI.submit_order] Error while calling Toast API: {str(e)}"
        ) from e

    if response.status == 200:
        # Convert the JSON string to a dictionary
        return Order.model_validate_json(response.decoded_body)
    else:
        logger.error(
            f"Order submission failed with status {response.status}: {response.decoded_body}"
        )
        raise ValueError(
            f"Order submission failed with status {response.status}: {response.decoded_body}"
        )
