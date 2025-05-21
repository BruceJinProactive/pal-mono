from typing import Optional

from tools.olo_tool._apis._utils import connect_olo_order_hub
from tools.olo_tool.classes import HttpMethod, OloAccessToken, OloBasket
from utils.log import logger


def get_customer_info():
    pass


def get_store_info():
    pass


def get_online_ordering_status():
    pass


def validate_address():
    pass


def create_basket(
    vendor_id: int, olo_token: OloAccessToken, auth_token: Optional[str] = None
) -> OloBasket:
    """
    Creates a basket for a vendor.

    Args:
        vendor_id (int): The vendor ID
        olo_token (OloAccessToken): The Olo access token
        auth_token (Optional[str], optional): The auth token. Defaults to None.

    Returns:
        OloBasket: A validated basket object from the API response
    """
    try:
        request_body = {
            "vendorid": vendor_id,
            "authtoken": auth_token,
        }
        response = connect_olo_order_hub(
            http_method=HttpMethod.POST,
            bearer_token=olo_token,
            api_function="/v1.1/baskets/create",
            query_params=None,
            payload=request_body,
        )
    except Exception as e:
        raise Exception(
            f"[OloTool._apis.create_basket] Error while calling Olo API: {str(e)}"
        ) from e

    if response.status == 200:
        return OloBasket.model_validate_json(response.decoded_body)
    else:
        logger.error(
            f"Failed to create basket with status {response.status}: {response.decoded_body}"
        )
        raise ValueError(
            f"Failed to create basket with status {response.status}: {response.decoded_body}"
        )


def add_items_to_basket():
    pass


def set_basket_handoff_mode():
    pass


def validate_basket():
    pass


def get_basket_details():
    pass


def request_ccsf_token():
    pass


def submit_order():
    pass
