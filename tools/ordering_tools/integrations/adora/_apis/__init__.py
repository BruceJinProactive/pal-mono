import http.client
import json
import os
import time
from datetime import date

import requests

from api.schemas.asset.asset import ReadAssetRequest, WriteAssetRequest
from services.asset_service import read_asset_by_name, write_asset
from tools.ordering_tools.classes import Consumer
from tools.ordering_tools.integrations.adora.classes import (
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
from utils.log import logger

from . import _utils

LOCAL_FASTAPI_ENDPOINT = "http://host.docker.internal:8000/v1/"


def get_adora_menu(store_id: str, bearer_token: AdoraAccessToken) -> dict | None:
    """
    Retrieve the store menu from Adora.

    Args:
        store_id (str): The store ID to retrieve the menu for.
        bearer_token (AdoraAccessToken): The bearer token to authenticate with Adora POS.

    Returns:
        dict | None: A dictionary of the store menu if successful, None otherwise.
    """

    FILENAME = f"pizzamyheart/<project_name>/menu-{store_id}.json"

    # Perform get to check if the asset exists
    read_request = ReadAssetRequest(name=FILENAME)
    asset_response = read_asset_by_name(read_request)

    if asset_response.url:
        # Response is 200 and not empty URL
        logger.info("Getting menu from s3 bucket via asset service.")

        # TODO: able to retrieve but getting 403
        url_response = requests.get(asset_response.url)

        url_response.raise_for_status()

        return url_response.json()
    else:
        # Fallback and connect to adora to get the menu
        response = _utils.connect_adora_order_hub(
            "GET",
            bearer_token,
            "menu",
            query_params={"sid": store_id},
            extra_headers=None,
            payload=None,
            logging=False,
        )

        if response.status == 200:
            logger.info("Uploading menu to s3 bucket via asset service.")

            json_content = response.decoded_body

            # Write to S3 bucket
            write_request = WriteAssetRequest(
                name=FILENAME, content=json_content.encode("utf-8")
            )
            write_asset(write_request)

            # Decode the JSON string once
            response_data = json.loads(json_content)

            # Check if the result is still a JSON string and decode again if necessary
            if isinstance(response_data, str):
                response_data = json.loads(response_data)  # return menu

            return response_data

    return None


def get_adora_pos_auth_token(key: str, secret: str) -> AdoraAccessToken | None:
    """
    Retrieve the store menu from Adora.

    Args:
        key (str): The Adora API Key.
        secret (str): The Adora API Secret.

    Returns:
        AdoraAccessToken: A bearer token that expires in 1 hour.
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


def get_wait_time(
    bearer_token: AdoraAccessToken,
    store_id: str,
) -> str | None:
    response = _utils.connect_adora_order_hub(
        "GET",
        bearer_token,
        "store/info",
        query_params={
            "sid": store_id,
            "date": date.today().isoformat(),
        },
        extra_headers=None,
        payload=None,
    )
    store_info = json.loads(response.decoded_body)

    if response.status == 200:
        return f'pickup wait time: {str(store_info["takeOutWaitTime"])}, delivery wait time: {str(store_info["deliveryWaitTime"])}'
    else:
        return None


def get_wait_time_with_strategy(
    bearer_token: AdoraAccessToken,
    store_id: str,
    strategy: str,
) -> int | None:
    response = _utils.connect_adora_order_hub(
        "GET",
        bearer_token,
        "store/info",
        query_params={
            "sid": store_id,
            "date": date.today().isoformat(),
        },
        extra_headers=None,
        payload=None,
    )
    store_info = json.loads(response.decoded_body)

    if response.status == 200:
        if strategy == "pickup":
            return store_info["takeOutWaitTime"]
        elif strategy == "delivery":
            return store_info["deliveryWaitTime"]
        else:
            return None
    else:
        return None


def validate_order(
    bearer_token: AdoraAccessToken,
    store_id: str,
    order_items: list[AdoraOrderItem],
    coupon_id: int,
    order_type: AdoraOrderType = AdoraOrderType.TakeOut,
    customer: Consumer = Consumer(
        first_name="Jimmy",
        last_name="ProactiveAiLab",
        phone_number="(555)555-5555",
        email="jimmythesurfer@proactiveailab.com",
    ),
    delivery_address: AdoraDeliveryAddress | None = None,
):
    """
    Validate a customer order in Adora system.

    Args:
        bearer_token (AdoraAccessToken): The bearer token to authenticate with Adora POS.
        store_id (str): The store ID to place the order with.
        order_items (list[AdoraOrderItem]): The list of items to be ordered.
        coupon_id (int): The coupon ID to apply to the order.
        order_type (AdoraOrderType, optional): The type of order (default is TakeOut).
        customer (Consumer, optional): The customer details (default is a predefined Consumer).
        delivery_address (AdoraDeliveryAddress | None, optional): The delivery address if the order is for delivery.

    Returns:
        dict: A dictionary containing the validation result with keys such as 'Key', 'IsPaymentRequired', 'SubTotal', 'Total', 'Discount', 'TaxAmount', 'ServiceCharge', and 'DeliveryCharge'.

    Example:
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

    full_item_list = []
    for order_item in order_items:
        full_item_list.append({"group": [order_item.to_dict()]})

    payload = {
        "storeId": store_id,
        "couponId": coupon_id,
        "orderType": order_type,
        "orderTypeSubType": "PhoneOrder",
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

    payload = json.dumps(payload, cls=_utils.DecimalEncoder)

    response = _utils.connect_adora_order_hub(
        "POST",
        bearer_token,
        "validateOrder",
        query_params=None,
        extra_headers=None,
        payload=payload,
    )

    if response.status == 200:
        return _utils.parse_json(AdoraOrderCalculationResult, response.decoded_body)
    else:
        logger.error(
            f"[AdoraIntegration._apis.validate_order] Order validation failed with status {response.status}: {response.decoded_body}"
        )
        return None


def save_validated_order(
    bearer_token: AdoraAccessToken,
    order_key: str,
) -> AdoraSavedOrderResult | None:
    """
    Save a customer's validated order in the system using the key from the validate_order response.

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
        return _utils.parse_json(AdoraSavedOrderResult, response.decoded_body)
    else:
        return None


def text_payment(
    bearer_token: AdoraAccessToken,
    order_id: int,
    store_id: str,
    phone_number: str,
) -> bool:
    """
    Send credit card payment link to the customer.

    Args:
        bearer_token (AdoraAccessToken): The bearer token to authenticate with Adora POS.
        order_id (int): The order ID from the save_validate_order response.
        store_id (str): The store ID to place the order with.
        phone_number (str): The phone number to associate with the order.

    Returns:
        bool: True if the order was placed successfully, False otherwise.
    """

    MAX_RETRIES = 5
    BASE_DELAY = 1  # second

    for attempt in range(MAX_RETRIES):
        try:
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
                        "customerPhoneNo": phone_number,
                    }
                ),
            )
            if response.status == 200:
                logger.debug(
                    f"[AdoraIntegration._apis.place_order] Order {order_id} placed successfully."
                )
                return True
            else:
                logger.warning(
                    f"[AdoraIntegration._apis.place_order] [Attempt {attempt + 1}/{MAX_RETRIES}] Failed to call connect_adora_order_hub:textPaymentUrl with order_id={order_id}, store_id={store_id}, phone_number={phone_number}. Status: {response.status}, Body: {response.decoded_body}"
                )
        except Exception as e:
            logger.error(
                f"[AdoraIntegration._apis.place_order] [Attempt {attempt + 1}/{MAX_RETRIES}] Failed to call connect_adora_order_hub:textPaymentUrl with order_id={order_id}, store_id={store_id}, phone_number={phone_number}. Exception: {type(e).__name__}: {e}"
            )

        delay = BASE_DELAY * (2**attempt)  # Exponential backoff
        logger.warning(
            f"[AdoraIntegration._apis.place_order] ... Retrying in {delay} seconds"
        )
        time.sleep(delay)

    logger.error(
        f"[AdoraIntegration._apis.place_order] [Attempt {MAX_RETRIES}/{MAX_RETRIES}] Failed to call connect_adora_order_hub:textPaymentUrl with order_id={order_id}, store_id={store_id}, phone_number={phone_number}."
    )
    return False


def validate_address(
    bearer_token: AdoraAccessToken, store_id: str, lat: str, long: str
) -> tuple[bool, list[AdoraValidatedAddress] | str]:
    """
    Validate an address (latitude + longitude) with Adora POS.

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
