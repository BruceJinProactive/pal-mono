import http.client
import json
from datetime import date
from typing import Any, Dict, List, Optional

from tools.adora_tool.classes import (
    AdoraAccessToken,
    AdoraDeliveryAddress,
    AdoraOrderCalculationResult,
    AdoraOrderItem,
    AdoraOrderType,
    AdoraSavedOrderResult,
    CustomerInfo,
)
from utils.log import logger

from . import _utils


def get_adora_pos_auth_token(key: str, secret: str) -> AdoraAccessToken | None:
    """
    Retrieve an Adora POS authentication token using the provided key and secret.

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


def get_online_ordering_status(
    bearer_token: AdoraAccessToken,
    store_id: str,
) -> str | None:
    response = _utils.connect_adora_order_hub(
        "GET",
        bearer_token,
        "store/status",
        query_params={"sid": store_id},
        extra_headers=None,
        payload=None,
    )
    status_info = json.loads(response.decoded_body)
    status = "active" if status_info["Online"] else "inactive"

    if response.status == 200:
        return f"The store is currently {status}."
    else:
        return None


def validate_order(bearer_token: AdoraAccessToken, json_payload: str):
    logger.info(f"[AdoraTool._apis.validate_order] Payload: {json_payload}")

    response = _utils.connect_adora_order_hub(
        "POST",
        bearer_token,
        "validateOrder",
        query_params=None,
        extra_headers=None,
        payload=json_payload,
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
