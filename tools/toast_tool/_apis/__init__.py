import http.client
import json
import urllib.parse
from typing import Optional

from tools.toast_tool._apis._utils import connect_toast_order_hub
from tools.toast_tool.classes import (
    DiningOption,
    InventoryResponse,
    Order,
    OrderingScheduleResponse,
    OrderInput,
    RestaurantInfo,
    RestaurantOrderingStatus,
    ToastAccessToken,
)
from tools.utils.ordering.classes import HttpMethod
from utils.log import logger

BASE_URL = "ws-sandbox-api.eng.toasttab.com"


def get_toast_access_token(
    client_id: str,
    client_secret: str,
    token_api_endpoint: str | None = None,
) -> Optional[ToastAccessToken]:
    """
    Obtains an access token from the Toast Authentication API.

    Args:
        client_id: Your Toast API client identifier
        client_secret: Your Toast API client secret
        token_api_endpoint: Optional custom token API endpoint

    Returns:
        `ToastAccessToken` object if successful, None otherwise
    """
    # Define constants for the API request
    USER_ACCESS_TYPE = "TOAST_MACHINE_CLIENT"

    payload = {
        "clientId": client_id,
        "clientSecret": client_secret,
        "userAccessType": USER_ACCESS_TYPE,
    }

    headers = {"Content-Type": "application/json"}

    logger.debug(
        f"[ToastAPI.get_toast_access_token] Authenticating with Toast API using client ID: {'*' * 8}{client_id[-4:] if len(client_id) > 4 else '*' * 4}"
    )

    # Determine which endpoint to use
    if token_api_endpoint:
        # Validate custom endpoint if provided
        try:
            # Handle cases where scheme might already be included
            if "://" in token_api_endpoint:
                parsed = urllib.parse.urlparse(token_api_endpoint)
                if parsed.scheme != "https":
                    raise ValueError("Only HTTPS endpoints are allowed")
            else:
                parsed = urllib.parse.urlparse(f"https://{token_api_endpoint}")

            if not parsed.netloc:
                raise ValueError("Invalid endpoint format")

        except Exception as e:
            raise ValueError(f"Invalid token_api_endpoint: {token_api_endpoint}") from e

        # Return the netloc only to ensure consistency
        endpoint = parsed.netloc
    else:
        endpoint = BASE_URL

    try:
        conn = http.client.HTTPSConnection(endpoint, timeout=30)
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

            # We don't need to check if the token is valid, the token pulled from API will always be valid

            logger.debug(
                f"[ToastAPI.get_toast_access_token] Successfully authenticated with Toast API expiring in: {token.expires_in} seconds"
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
    general_api_endpoint: str | None = None,
) -> RestaurantInfo:
    """
    Get restaurant information from the Toast API.

    Args:
        bearer_token: Toast access token
        store_id: External ID for the restaurant
        include_archived: Whether to include archived restaurants
        general_api_endpoint: Optional custom API endpoint

    Returns:
        RestaurantInfo object
    """
    query_params = {"includeArchived": str(include_archived).lower()}
    try:
        response = connect_toast_order_hub(
            http_method=HttpMethod.GET,
            bearer_token=bearer_token,
            api_function=f"/restaurants/v1/restaurants/{store_id}",
            store_id=store_id,
            query_params=query_params,
            extra_headers=None,
            payload=None,
            general_api_endpoint=general_api_endpoint,
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
    general_api_endpoint: str | None = None,
) -> RestaurantOrderingStatus:
    """
    Get the online ordering availability status for a Toast restaurant.

    Args:
        bearer_token: Toast access token
        store_id: External ID for the restaurant
        general_api_endpoint: Optional custom API endpoint

    Returns:
        RestaurantOrderingStatus object containing the availability status
        or raises an exception if the request fails.
    """
    try:
        response = connect_toast_order_hub(
            http_method=HttpMethod.GET,
            bearer_token=bearer_token,
            api_function="/restaurant-availability/v1/availability",
            store_id=store_id,
            query_params=None,
            extra_headers=None,
            payload=None,
            general_api_endpoint=general_api_endpoint,
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
    order_data: OrderInput,
    general_api_endpoint: str | None = None,
) -> Order:
    """
    Calculates the check price amounts, tax amounts, and service charges for an OrderInput object.

    Args:
        bearer_token: Toast access token
        store_id: External ID for the restaurant
        order_data: OrderInput object containing the order details
        general_api_endpoint: Optional custom API endpoint

    Returns:
        `Order` object with the base price, tax amount, and total price of each `check` object. The returned `Order` object will be used to submit the order to the Toast API.
    """
    # Make the API call to the order prices endpoint
    try:
        response = connect_toast_order_hub(
            http_method=HttpMethod.POST,
            bearer_token=bearer_token,
            api_function="/orders/v2/prices",
            store_id=store_id,
            query_params=None,
            payload=order_data.model_dump(exclude_none=True),
            general_api_endpoint=general_api_endpoint,
        )
    except Exception as e:
        raise Exception(
            f"[ToastAPI.get_order_prices] Error while calling Toast API: {str(e)}"
        ) from e

    # Process the response
    if response.status == 200:
        # Convert the JSON string to an Order object
        decoded_body = response.decoded_body
        order_prices = Order.model_validate_json(decoded_body)

        return order_prices
    else:
        logger.error(
            f"Order price calculation failed with status {response.status}: {response.decoded_body}"
        )
        raise ValueError(
            f"Order price calculation failed with status {response.status}: {response.decoded_body}"
        )


def get_dining_options(
    bearer_token: ToastAccessToken,
    store_id: str,
) -> list[DiningOption]:
    """
    Retrieves available dining options from the Toast API for a restaurant.

    Args:
        bearer_token: Toast access token
        store_id: External ID for the restaurant

    Returns:
        List of DiningOption objects containing the available dining options, or raises an exception if the request fails.
    """
    try:
        response = connect_toast_order_hub(
            http_method=HttpMethod.GET,
            bearer_token=bearer_token,
            api_function="/config/v2/diningOptions",
            store_id=store_id,
            query_params=None,
            payload=None,
        )
    except Exception as e:
        raise Exception(
            f"[ToastAPI.get_dining_options] Error while calling Toast API: {str(e)}"
        ) from e

    response_data = response.decoded_body
    if response.status == 200:

        # Convert the JSON string to an Order object
        dining_options = [
            DiningOption.model_validate_json(json.dumps(option))
            for option in json.loads(response_data)
        ]
        # Return the list of DiningOption objects
        return dining_options
    else:
        raise ValueError(
            f"Failed to get dining options with status {response.status}: {response_data}"
        )


def get_dining_option(
    bearer_token: ToastAccessToken,
    store_id: str,
    dining_option_id: str,
) -> DiningOption:
    try:
        response = connect_toast_order_hub(
            http_method=HttpMethod.GET,
            bearer_token=bearer_token,
            api_function=f"/config/v2/diningOptions/{dining_option_id}",
            store_id=store_id,
            query_params=None,
            payload=None,
        )
    except Exception as e:
        raise Exception(
            f"[ToastAPI.get_dining_option] Error while calling Toast API: {str(e)}"
        ) from e

    response_data = response.decoded_body
    if response.status == 200:

        # Convert the JSON string to an Order object
        dining_option = DiningOption.model_validate_json(response_data)
        # Return the list of DiningOption objects
        return dining_option
    else:
        raise ValueError(
            f"Failed to get dining option with status {response.status}: {response_data}"
        )


def submit_order(
    bearer_token: ToastAccessToken,
    store_id: str,
    order: OrderInput,
    general_api_endpoint: str | None = None,
) -> Order:
    """
    Submits an order to the Toast API.

    Args:
        bearer_token: The Toast access token
        store_id: The external ID of the restaurant
        order: The OrderInput object to be submitted
        general_api_endpoint: Optional custom API endpoint

    Returns:
        Order object that has been persisted in Toast.
    """
    try:
        response = connect_toast_order_hub(
            http_method=HttpMethod.POST,
            bearer_token=bearer_token,
            api_function="/orders/v2/orders",
            store_id=store_id,
            payload=order.model_dump(exclude_none=True),
            general_api_endpoint=general_api_endpoint,
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


def get_menu_inventory(
    bearer_token: ToastAccessToken,
    store_id: str,
    status: Optional[str] = None,
) -> InventoryResponse:
    """
    Retrieves menu inventory information from the Toast API.
    Returns inventory information for all menu items that have an OUT_OF_STOCK or QUANTITY status.

    Args:
        bearer_token (ToastAccessToken): The Toast access token.
        store_id (str): The external ID of the restaurant.
        status (Optional[str]): Filter by stock status (OUT_OF_STOCK or QUANTITY).
                               If None, returns items with both statuses.

    Returns:
        InventoryResponse: Contains list of inventory items with their stock information.
    """
    # Prepare query parameters
    query_params = {}
    if status:
        if status not in ["OUT_OF_STOCK", "QUANTITY"]:
            raise ValueError("Status must be either 'OUT_OF_STOCK' or 'QUANTITY'")
        query_params["status"] = status

    try:
        response = connect_toast_order_hub(
            http_method=HttpMethod.GET,
            bearer_token=bearer_token,
            api_function="/stock/v1/inventory",
            store_id=store_id,
            query_params=query_params if query_params else None,
            payload=None,
        )
    except Exception as e:
        raise Exception(
            f"[ToastAPI.get_menu_inventory] Error while calling Toast API: {str(e)}"
        ) from e

    if response.status == 200:
        # Convert the JSON string to an InventoryResponse object
        inventory_data = json.loads(response.decoded_body)
        return InventoryResponse(items=inventory_data)
    else:
        logger.error(
            f"Inventory retrieval failed with status {response.status}: {response.decoded_body}"
        )
        raise ValueError(
            f"Inventory retrieval failed with status {response.status}: {response.decoded_body}"
        )


def get_ordering_schedule(
    bearer_token: ToastAccessToken,
    store_id: str,
    general_api_endpoint: str | None = None,
) -> OrderingScheduleResponse:
    """
    Retrieves online ordering schedule information from the Toast API.
    Returns information about when the restaurant accepts online orders,
    including service periods, overrides, and scheduling configurations.

    Args:
        bearer_token (ToastAccessToken): The Toast access token.
        store_id (str): The external ID of the restaurant.

    Returns:
        OrderingScheduleResponse: Contains online ordering schedule information including:
            - Service periods with day/time ranges
            - Override schedules for special dates
            - Last order configuration settings
            - Maximum days for scheduled orders
            - Restaurant time zone
    """
    try:
        # The Toast ordering schedule API requires the store_id as a header parameter
        extra_headers = {"Toast-Restaurant-External-ID": store_id}

        response = connect_toast_order_hub(
            http_method=HttpMethod.GET,
            bearer_token=bearer_token,
            api_function="/ordermgmt-config/v1/published/orderingSchedule",
            store_id=store_id,
            extra_headers=extra_headers,
            query_params=None,
            payload=None,
            general_api_endpoint=general_api_endpoint,
        )
    except Exception as e:
        raise Exception(
            f"[ToastAPI.get_ordering_schedule] Error while calling Toast API: {str(e)}"
        ) from e

    if response.status == 200:
        # Convert the JSON string to an OrderingScheduleResponse object
        return OrderingScheduleResponse.model_validate_json(response.decoded_body)
    else:
        logger.error(
            f"Ordering schedule retrieval failed with status {response.status}: {response.decoded_body}"
        )
        raise ValueError(
            f"Ordering schedule retrieval failed with status {response.status}: {response.decoded_body}"
        )


def get_existing_order(
    bearer_token: ToastAccessToken,
    store_id: str,
    order_guid: str,
    general_api_endpoint: str | None = None,
) -> Optional[Order]:
    """
    Retrieves an existing order from the Toast API by its GUID.

    Args:
        bearer_token (ToastAccessToken): The Toast access token.
        store_id (str): The external ID of the restaurant.
        order_guid (str): The GUID of the order to retrieve.
        general_api_endpoint (str | None): Optional custom API endpoint.

    Returns:
        Optional[Order]: The order object with all its details if found, None if not found (404).
    """
    try:
        response = connect_toast_order_hub(
            http_method=HttpMethod.GET,
            bearer_token=bearer_token,
            api_function=f"/orders/v2/orders/{order_guid}",
            store_id=store_id,
            general_api_endpoint=general_api_endpoint,
        )
    except Exception as e:
        raise Exception(
            f"[ToastAPI.get_existing_order] Error while calling Toast API: {str(e)}"
        ) from e

    if response.status == 200:
        # Convert the JSON string to an Order object
        return Order.model_validate_json(response.decoded_body)
    elif response.status == 404:
        logger.debug(
            f"[ToastAPI.get_existing_order] Order with GUID {order_guid} not found."
        )
        return None
    else:
        logger.error(
            f"Order retrieval failed with status {response.status}: {response.decoded_body}"
        )
        raise ValueError(
            f"Order retrieval failed with status {response.status}: {response.decoded_body}"
        )
