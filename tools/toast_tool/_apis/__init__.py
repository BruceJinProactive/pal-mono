from typing import List, Optional

from tools.toast_tool.classes import Order, ToastAccessToken


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
        ToastAccessToken if successful, None otherwise
    """
    # TODO: implment the following variables as constants
    # 1. toast_api_hostname: str = "toast-api-server"
    # 2. user_access_type: str = "TOAST_MACHINE_CLIENT"
    pass


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
