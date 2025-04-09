import http.client
import json
from typing import Optional

from tools.toast_tool._apis._utils import API_TIMEOUT
from tools.toast_tool.classes import Order, ToastAccessToken
from utils.log import logger


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
) -> dict | None:
    """
    Get restaurant information from the Toast API.

    Args:
        bearer_token: Toast access token
        store_id: External ID for the restaurant
        include_archived: Whether to include archived restaurants

    Returns:
        Restaurant information as a dictionary or None if request failed

    {
        "guid": "string",
        "general": {},
        "urls": {},
        "location": {},
        "schedules": {},
        "delivery": {},
        "onlineOrdering": {},
        "prepTimes": {}
    }
    """
    pass


def get_online_ordering_status(
    bearer_token: ToastAccessToken,
    store_id: str,
    logging_enabled: bool = True,
) -> str | None:
    """
    Get the online ordering availability status for a Toast restaurant.

    Args:
        bearer_token: Toast access token
        store_id: External ID for the restaurant
        logging_enabled: Whether to log request and response details

    Returns:
        String describing the availability status, or None if request failed

    {
        "restaurantGuid": "string",
        "status": "ONLINE",
        "reasonKey": "AVAILABILITY_ONLINE",
        "reason": "string"
    }
    """
    pass


def get_order_prices(
    bearer_token: ToastAccessToken,
    store_id: str,
    order_data: Order,
) -> Order | None:
    """
    Calculates the check price amounts, tax amounts, and service charges for an Order object.

    Args:
        bearer_token: Toast access token
        store_id: External ID for the restaurant
        order_data: Order object containing the order details

    Returns:
        `Order` object with the base price, tax amount, and total price of each `check`. The returned `Order` object will be used to submit the order to the Toast API.

    {
        "guid": "string",
        "entityType": "string",
        "externalId": "string",
        "openedDate": "2025-02-07T08:00:00.000-0800",
        "modifiedDate": "2025-02-07T08:00:00.000-0800",
        "promisedDate": "2025-05-01T08:00:00.000-0800",
        "channelGuid": "3c66b5cf-1850-49e6-aef3-40576e6de979",
        "diningOption": {},
        "checks": [],
        "table": {},
        "serviceArea": {},
        "restaurantService": {},
        "revenueCenter": {},
        "source": "string",
        "duration": 0,
        "deliveryInfo": {},
        "requiredPrepTime": "string",
        "estimatedFulfillmentDate": "2025-05-01T08:00:00.000-0800",
        "numberOfGuests": 0,
        "voided": true,
        "voidDate": "2025-02-07T08:00:00.000-0800",
        "voidBusinessDate": 0,
        "paidDate": "2025-02-07T08:00:00.000-0800",
        "closedDate": "2025-02-07T08:00:00.000-0800",
        "deletedDate": "2025-02-07T08:00:00.000-0800",
        "deleted": true,
        "businessDate": 0,
        "server": {},
        "pricingFeatures": [],
        "approvalStatus": "NEEDS_APPROVAL",
        "guestOrderStatus": "string",
        "createdDevice": {},
        "createdDate": "2025-02-07T08:00:00.000-0800",
        "initialDate": 0,
        "lastModifiedDevice": {},
        "curbsidePickupInfo": {},
        "deliveryServiceInfo": {},
        "marketplaceFacilitatorTaxInfo": {},
        "createdInTestMode": true,
        "appliedPackagingInfo": {},
        "excessFood": true,
        "displayNumber": "string"
    }
    """
    pass


def submit_order(
    bearer_token: ToastAccessToken, store_id: str, order: Order
) -> Order | None:
    """
    Submits an order to the Toast API.

    Args:
        bearer_token (ToastAccessToken): The Toast access token.
        store_id (str): The external ID of the restaurant.
        order (Order): The Order object to be submitted.

    Returns:
        `Order` object that has been persisted in Toast.
    """
    pass
