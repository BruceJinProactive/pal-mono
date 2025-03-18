import http.client
import json
from datetime import datetime

from tools.adora_tool.classes import (
    AdoraAccessToken,
    AdoraOrderCalculationResult,
    AdoraSavedOrderResult,
    AdoraValidatedAddress,
    AdoraValidatedAddressList,
)
from utils.log import logger

from . import _utils


def get_adora_pos_auth_token(
    key: str, secret: str, qa_store: bool
) -> AdoraAccessToken | None:
    """
    Retrieve an Adora POS authentication token using the provided key and secret.

    Args:
        key (str): The Adora API Key.
        secret (str): The Adora API Secret.
        qa_store (bool): True if the QA environment should be used.

    Returns:
        AdoraAccessToken: A bearer token that expires in 1 hour.
    """
    if not key or not secret:
        return None
    payload = (
        "grant_type=client_credentials&client_id=" + key + "&client_secret=" + secret
    )
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    if qa_store:
        conn = http.client.HTTPSConnection("identityqa.adorapos.com")
    else:
        conn = http.client.HTTPSConnection("identity.adorapos.net")

    conn.request("POST", "/connect/token", payload, headers)
    res = conn.getresponse()
    data = res.read()
    bearer_token_json = data.decode("utf-8")

    return _utils.parse_json(AdoraAccessToken, bearer_token_json)


def get_customer_info(
    bearer_token: AdoraAccessToken, store_id: str, phone_number: str, qa_store: bool
) -> str | None:
    response = _utils.connect_adora_order_hub(
        "GET",
        bearer_token,
        "customer",
        query_params={
            "phone": phone_number,
            "sid": store_id,
        },
        extra_headers=None,
        payload=None,
        qa_store=qa_store,
    )

    customer_info = json.loads(response.decoded_body)

    # Customer does not exist
    if isinstance(customer_info, str):
        return ""

    name = f"Customer name: {customer_info['name']} {customer_info['lastname']}\n\n"

    if len(customer_info["addresses"]) > 0:
        addresses = "Addresses:\n\n"

        for addr in customer_info["addresses"]:
            addresses += (
                f"{addr['streetNo']} {addr['address']}, "
                f"{addr['city']}, {addr['state']}, "
                f"{addr['zip']}\n\n"
            )
    else:
        addresses = ""

    if response.status == 200:
        return name + addresses
    else:
        return None


def get_online_ordering_status(
    bearer_token: AdoraAccessToken, store_id: str, qa_store: bool
) -> str | None:
    response = _utils.connect_adora_order_hub(
        "GET",
        bearer_token,
        "store/status",
        query_params={"sid": store_id},
        extra_headers=None,
        payload=None,
        qa_store=qa_store,
    )
    status_info = json.loads(response.decoded_body)
    status = "active" if status_info["Online"] else "inactive"

    if response.status == 200:
        return f"The store is currently {status}."
    else:
        return None


def get_wait_time(
    bearer_token: AdoraAccessToken, store_id: str, date: str, qa_store: bool
) -> str | None:
    response = _utils.connect_adora_order_hub(
        "GET",
        bearer_token,
        "store/info",
        query_params={
            "sid": store_id,
            "date": date,
        },
        extra_headers=None,
        payload=None,
        qa_store=qa_store,
    )

    store_info = json.loads(response.decoded_body)

    if response.status == 200:
        return f'Pickup wait time: {str(store_info["takeOutWaitTime"])}, Delivery wait time: {str(store_info["deliveryWaitTime"])}'
    else:
        return None


def validate_order(
    bearer_token: AdoraAccessToken, payload: str, qa_store: bool
) -> AdoraOrderCalculationResult | None:
    logger.info(f"[AdoraTool._apis.validate_order] Payload: {payload}")

    response = _utils.connect_adora_order_hub(
        "POST",
        bearer_token,
        "validateOrder",
        query_params=None,
        extra_headers=None,
        payload=payload,
        qa_store=qa_store,
    )

    if response.status == 200:
        return _utils.parse_json(AdoraOrderCalculationResult, response.decoded_body)
    else:
        logger.error(
            f"[AdoraTool._apis.validate_order] Order validation failed with status {response.status}: {response.decoded_body}"
        )
        return None


def save_validated_order(
    bearer_token: AdoraAccessToken,
    order_key: str,
    qa_store: bool,
) -> AdoraSavedOrderResult | None:
    """
    Save a customer's validated order in the system using the key from the validate_order response.

    Args:
        bearer_token (AccessToken): The bearer token to authenticate with Adora POS.
        order_key (str): The order key from the validate_order response.
        qa_store (bool): True if the QA environment should be used.

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
        qa_store=qa_store,
    )

    if response.status == 200:
        return _utils.parse_json(AdoraSavedOrderResult, response.decoded_body)
    else:
        return None


def validate_address(
    bearer_token: AdoraAccessToken,
    store_id: str,
    lat: float,
    long: float,
    qa_store: bool,
) -> tuple[bool, list[AdoraValidatedAddress] | str]:
    """
    Validate an address (latitude + longitude) with Adora POS.

    Args:
        bearer_token (AccessToken): The bearer token to authenticate with Adora POS.
        store_id (str): The store ID.
        lat (str): The latitude of the address.
        long (str): The longitude of the address.
        qa_store (bool): True if the QA environment should be used.

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
        qa_store=qa_store,
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
