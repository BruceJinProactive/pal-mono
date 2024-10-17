import http.client
import json
from datetime import datetime, timedelta, timezone

from ai.tools.ordering_tools.classes import Consumer
from ai.tools.ordering_tools.integrations.adora.classes import (
    AdoraAccessToken,
    AdoraCoupon,
    AdoraCouponList,
    AdoraDeliveryAddress,
    AdoraOrderCalculationResult,
    AdoraOrderItem,
    AdoraOrderType,
    AdoraSavedOrderResult,
    AdoraValidatedAddress,
    AdoraValidatedAddressList,
)

from . import _utils


def get_adora_menu(store_id: str, bearer_token: AdoraAccessToken) -> dict | None:
    """
    Returns a dictionary of the store menu
    maps to Adora API doc: https://adoraimages.blob.core.windows.net/api-docs/orderhubapi.html#tag/OrderHub/paths/~1api~1v%7Bversion%7D~1OrderHub~1menu/get
    """
    response = _utils.connect_adora_order_hub(
        "GET",
        bearer_token,
        "menu",
        query_params={"sid": store_id},
        extra_headers=None,
        payload=None,
    )

    if response.status == 200:
        # Decode the JSON string once
        response_data = json.loads(response.decoded_body)

        # Check if the result is still a JSON string and decode again if necessary
        if isinstance(response_data, str):
            response_data = json.loads(response_data)

        return response_data
    else:
        return None


def get_adora_pos_auth_token(key: str, secret: str) -> AdoraAccessToken | None:
    """
    Returns a bearer token. It expires in 1 hour.
    """
    if not key or not secret:
        return None
    payload = (
        "grant_type=client_credentials&client_id=" + key + "&client_secret=" + secret
    )
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    conn = http.client.HTTPSConnection("identity.adorapos.net")
    conn.request("POST", "/connect/token", payload, headers)
    res = conn.getresponse()
    data = res.read()
    bearer_token_json = data.decode("utf-8")

    return _utils.parse_json(AdoraAccessToken, bearer_token_json)


def validate_order(
    bearer_token: AdoraAccessToken,
    store_id: str,
    order_items: list[AdoraOrderItem],
    coupon_id: int,
    order_type: AdoraOrderType = AdoraOrderType.TakeOut,
    customer: Consumer = Consumer(
        first_name="JimmyAI",
        last_name="ValidateOrder",
        phone_number="(555)555-5555",
        email="jimmythesurfer@proactiveailab.com",
    ),
    delivery_address: AdoraDeliveryAddress | None = None,
):
    """
    Validate order with Adora Pos
    maps to Adora API doc: https://adoraimages.blob.core.windows.net/api-docs/orderhubapi.html#tag/OrderHub/paths/~1api~1v%7Bversion%7D~1OrderHub~1validateOrder/post
    Example success return value with http status 200:
    {
        "Key": "d0a91931-60e8-4ff4-a38d-876f13dabb9c",
        "IsPaymentRequired": true,
        "SubTotal": 39.50,
        "Total": 43.15,
        "Discount": 0.00,
        "TaxAmount": 3.65,
        "ServiceCharge": 0.00,
        "DeliveryCharge": 0.00
    }
    """

    assert order_type == AdoraOrderType.TakeOut or (
        order_type == AdoraOrderType.Delivery and delivery_address
    ), "Invalid order type, either takeout or need address for delivery"

    # NOTE: Adoro API says "promiseDateTime" is optional, but it's actually required, and it's required to be
    # less than 24 hours (or 12 hours, need trial and error testing) in the future. Need to check with their Eng to figure out why.
    # In the mean time, we just create a datatime that's 2 hour in the future to satify Adora Pos API requirement.
    current_datetime = datetime.now(timezone.utc)
    future_datetime = current_datetime + timedelta(hours=2)
    formatted_datetime = future_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")

    full_item_list = []
    for order_item in order_items:
        full_item_list.append({"group": [order_item.__dict__]})

    payload = {
        "storeId": store_id,
        "couponId": coupon_id,
        "orderType": order_type,
        "orderTypeSubType": "PhoneOrder",
        "promiseDateTime": formatted_datetime,
        "customer": {
            "name": customer.first_name,
            "lastname": customer.last_name,
            "phone": customer.phone_number,
            "email": customer.email,
        },
        "items": full_item_list,
        "discount": 0,
        "paid": False,
        "orderComment": " ",
    }

    # add delivery address
    if order_type == AdoraOrderType.Delivery and delivery_address:
        payload["deliveryAddress"] = delivery_address.model_dump()

    payload = json.dumps(payload)

    response = _utils.connect_adora_order_hub(
        "POST",
        bearer_token,
        "validateOrder",
        query_params=None,
        extra_headers=None,
        payload=payload,
    )

    if response.status == 200:
        return _utils.parse_json(
            AdoraOrderCalculationResult, json.loads(response.decoded_body)
        )
    else:
        return None


def save_validate_order(
    bearer_token: AdoraAccessToken,
    order_key: str,
) -> AdoraSavedOrderResult | None:
    """Save an already-validate order to Adora POS.

    Args:
        bearer_token (AccessToken): The bearer token to authenticate with Adora POS.
        order_key (str): The order key from the validate_order response.

    Returns:
        SavedOrderResult: The result of saving the order to Adora POS.
    """
    response = _utils.connect_adora_order_hub(
        "POST",
        bearer_token,
        "save",
        query_params=None,
        extra_headers={
            "orderKey": order_key,
        },
    )

    if response.status == 200:
        return _utils.parse_json(
            AdoraSavedOrderResult, json.loads(response.decoded_body)
        )
    else:
        return None


def place_order(
    bearer_token: AdoraAccessToken,
    order_id: int,
    store_id: str,
    phone_number: str,
) -> bool:
    """Place an order with Adora POS.

    Args:
        bearer_token (AccessToken): The bearer token to authenticate with Adora POS.
        order_id (int): The order ID from the save_validate_order response.
        store_id (str): The store ID to place the order with.
        phone_number (str): The phone number to associate with the order.

    Returns:
        bool: True if the order was placed successfully, False otherwise.
    """
    response = _utils.connect_adora_order_hub(
        "POST",
        bearer_token,
        "textPaymentUrl",
        query_params=None,
        extra_headers=None,
        payload=json.dumps(
            {"orderId": order_id, "storeId": store_id, "customerPhoneNo": phone_number}
        ),
    )

    if response.status == 200:
        return True  # Adora does not return anything useful for this API endpoint, so just return True
    else:
        return False


def validate_address(
    bearer_token: AdoraAccessToken, store_id: str, lat: str, long: str
) -> tuple[bool, list[AdoraValidatedAddress] | str]:
    """Validate an address (latitude + longitude) with Adora POS.

    Args:
        bearer_token (AccessToken): The bearer token to authenticate with Adora POS.
        store_id (str): The store ID.
        lat (str): The latitude of the address.
        long (str): The longitude of the address.

    Returns:
        bool: True if the address was validated successfully, False otherwise.
        list[ValidatedAddress] | str: A list of validated addresses if the address was validated successfully,
            or an error message otherwise.
    """
    response = _utils.connect_adora_order_hub(
        "POST",
        bearer_token,
        "validateAddress",
        query_params=None,
        extra_headers=None,
        payload=json.dumps({"storeId": store_id, "lat": lat, "lng": long}),
    )

    if response.status == 200:
        parsed_json = _utils.parse_json(
            AdoraValidatedAddressList,
            # account for weird Adora API response format of a string of an array
            json.dumps({"addresses": json.loads(json.loads(response.decoded_body))}),
        )
        return (
            (True, parsed_json.addresses)
            if parsed_json
            else (False, "An error occurred.")
        )
    else:
        # return error message, likely "Address was not found in the list of delivery zones!"
        return False, response.decoded_body


def list_coupons(
    bearer_token: AdoraAccessToken,
    store_id: str,
) -> list[AdoraCoupon]:
    response = _utils.connect_adora_order_hub(
        "GET",
        bearer_token,
        "coupons",
        query_params={
            "sid": store_id,
        },
        extra_headers=None,
        payload=None,
    )

    if response.status == 200:
        # parse Adora array of coupons into a list of Coupon objects
        parsed_json = _utils.parse_json(
            AdoraCouponList, json.dumps({"coupons": json.loads(response.decoded_body)})
        )

        return parsed_json.coupons if parsed_json else []
    else:
        return []
