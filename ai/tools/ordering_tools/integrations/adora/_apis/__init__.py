import http
import json
from datetime import datetime, timedelta, timezone

from ai.tools.ordering_tools.integrations.adora.classes import (
    AccessToken,
    AdoraOrderItem,
    Consumer,
    OrderCalculationResult,
    OrderType,
    SavedOrderResult,
)

from . import _utils


def get_adora_pos_auth_token(key: str, secret: str):
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

    return _utils.parse_json(AccessToken, bearer_token_json)


def validate_order(
    bearer_token: AccessToken,
    store_id: str,
    # order_items: list[OrderItem],
    order_item: AdoraOrderItem,
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

    # TODO use place holder user info for calculating fees
    # Adora API won't work if we are missing User Info.
    customer: Consumer = Consumer(
        first_name="Agent",
        last_name="Smith",
        phone_number="(888)123-4567",
        email="GKvzQ@example.com",
    )

    order_type = OrderType.TakeOut
    delivery_address = None

    assert order_type == OrderType.TakeOut or (
        order_type == OrderType.Delivery and delivery_address
    ), "Invalid order type, either takeout or need address for delivery"

    # NOTE: Adoro API says "promiseDateTime" is optional, but it's actually required, and it's required to be
    # less than 24 hours (or 12 hours, need trial and error testing) in the future. Need to check with their Eng to figure out why.
    # In the mean time, we just create a datatime that's 2 hour in the future to satify Adora Pos API requirement.
    current_datetime = datetime.now(timezone.utc)
    future_datetime = current_datetime + timedelta(hours=2)
    formatted_datetime = future_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")

    # item_list = []
    # for order_item in order_items:
    #     item_list.append({"group": [order_item]})

    payload = {
        "storeId": store_id,
        "couponId": 0,
        "orderType": order_type,
        "orderTypeSubType": "PhoneOrder",
        "promiseDateTime": formatted_datetime,
        "customer": {
            "name": customer.first_name,
            "lastname": customer.last_name,
            "phone": customer.phone_number,
            "email": customer.email,
        },
        "items": [{"group": [order_item.__dict__]}],
        "discount": 0,
        "paid": False,
        "orderComment": " ",
    }

    # add delivery address
    if order_type == OrderType.Delivery and delivery_address:
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
            OrderCalculationResult, json.loads(response.decoded_body)
        )
    else:
        return None


def save_validate_order(
    bearer_token: AccessToken,
    order_key: str,
):
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
        return _utils.parse_json(SavedOrderResult, json.loads(response.decoded_body))
    else:
        return None


def place_order(
    bearer_token: AccessToken,
    order_id: int,
    store_id: str,
):
    response = _utils.connect_adora_order_hub(
        "POST",
        bearer_token,
        "textPaymentUrl",
        query_params=None,
        extra_headers=None,
        payload=json.dumps(
            {
                "orderId": order_id,
                "storeId": store_id,
                "customerPhoneNo": "(888)123-4567",  # TODO how do we retrieve this?
            }
        ),
    )

    if response.status == 200:
        return True
    else:
        return False
