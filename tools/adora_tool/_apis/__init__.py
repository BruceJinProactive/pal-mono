import http.client
import json
from datetime import date

from tools.adora_tool.classes import AdoraAccessToken
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
