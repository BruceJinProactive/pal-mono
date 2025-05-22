import json
from typing import Optional

from tools.olo_tool._apis._utils import connect_olo_order_hub
from tools.olo_tool.classes import (
    Address,
    BillingScheme,
    DeliveryAddressValidationResponse,
    HttpMethod,
    OloAccessToken,
    OloBasket,
    OloBasketHandoffMode,
    OloCCSFToken,
    OloOrderSubmissionBody,
    OloOrderSubmissionResponse,
    OloProductInput,
    OloStore,
    ValidatedBasketTotals,
)
from utils.log import logger


def get_store_info(restaurant_id: int, olo_token: OloAccessToken) -> OloStore:
    """
    Get the store info for a given restaurant ID

    Args:
        restaurant_id (int): The restaurant ID
        olo_token (OloAccessToken): The Olo access token

    Returns:
        OloStore: A validated store object from the API response
    """
    try:
        response = connect_olo_order_hub(
            http_method=HttpMethod.GET,
            bearer_token=olo_token,
            api_function=f"/v1.1/restaurants/{restaurant_id}",
            query_params=None,
            payload=None,
        )
    except Exception as e:
        raise Exception(
            f"[OloTool._apis.get_store_info] Error while calling Olo API: {str(e)}"
        ) from e

    if response.status == 200:
        return OloStore.model_validate_json(response.decoded_body)
    else:
        logger.error(
            f"Failed to get store info for restaurant {restaurant_id} with status {response.status}: {response.decoded_body}"
        )
        raise ValueError(
            f"Failed to get store info for restaurant {restaurant_id} with status {response.status}: {response.decoded_body}"
        )


def get_online_ordering_status(
    restaurant_id: int, olo_token: OloAccessToken
) -> Optional[int]:
    """
    Get the online ordering status for ONE given restaurant ID

    Args:
        restaurant_id (int): The restaurant ID
        olo_token (OloAccessToken): The Olo access token

    Returns:
        int | None: Current estimated ASAP order lead time in minutes. None if the restaurant is not accepting online orders.
    """
    try:
        request_body = {
            "vendorids": [restaurant_id],
        }
        response = connect_olo_order_hub(
            http_method=HttpMethod.POST,
            bearer_token=olo_token,
            api_function="/v1.1/restaurants/capacity/leadtimes",
            query_params=None,
            payload=request_body,
        )
    except Exception as e:
        raise Exception(
            f"[OloTool._apis.get_online_ordering_status] Error while calling Olo API: {str(e)}"
        ) from e

    if response.status == 200:
        response_json = json.loads(response.decoded_body)
        if len(response_json["leadtimes"]) > 0:
            return response_json["leadtimes"][0]["totalminutes"]
        else:
            raise ValueError(
                f"No leadtime data found for restaurant {restaurant_id}.\nMessage: {response_json['errors']}"
            )
    else:
        logger.error(
            f"Failed to get online ordering status for restaurant {restaurant_id} with status {response.status}: {response.decoded_body}"
        )
        raise ValueError(
            f"Failed to get online ordering status for restaurant {restaurant_id} with status {response.status}: {response.decoded_body}"
        )


def validate_address(
    restaurant_id: int, address: Address, olo_token: OloAccessToken
) -> DeliveryAddressValidationResponse:
    """
    Validates an address for a given restaurant ID.

    Args:
        restaurant_id (int): The restaurant ID
        address (Address): The address to validate
        olo_token (OloAccessToken): The Olo access token

    Returns:
        DeliveryAddressValidationResponse: A validated address response object from the API response
    """
    try:
        request_body = {
            "handoffmode": "delivery",  # Enum: "delivery" "dispatch". We only handle delivery for now.
            "timewantedmode": "asap",  # Enum: "asap" "advance". We only handle ASAP for now.
            "street": address.streetaddress,
            "city": address.city,
            "zipcode": address.zipcode,
            # The time the user wants the order to be ready, formatted "yyyymmdd hh:mm". Only send if timewantedmode is "advance". We ONLY handle ASAP for now.
            "timewantedutc": None,
        }
        response = connect_olo_order_hub(
            http_method=HttpMethod.POST,
            bearer_token=olo_token,
            api_function=f"/v1.1/restaurants/{restaurant_id}/checkdeliverycoverage",
            query_params=None,
            payload=request_body,
        )
    except Exception as e:
        raise Exception(
            f"[OloTool._apis.validate_address] Error while calling Olo API: {str(e)}"
        ) from e

    if response.status == 200:
        return DeliveryAddressValidationResponse.model_validate_json(
            response.decoded_body
        )
    else:
        logger.error(
            f"Failed to validate address for restaurant {restaurant_id} with status {response.status}: {response.decoded_body}"
        )
        raise ValueError(
            f"Failed to validate address for restaurant {restaurant_id} with status {response.status}: {response.decoded_body}"
        )


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


def add_items_to_basket(
    basket_id: str, olo_token: OloAccessToken, olo_product_input: OloProductInput
) -> dict:
    """
    Adds items to a basket.

    Args:
        basket_id (str): The basket ID
        olo_token (OloAccessToken): The Olo access token
        olo_product_input (OloProductInput): The Olo product input

    Returns:
        dict: A dictionary containing the new basket (OloBasket) and a list of errors
    """
    try:
        request_body = olo_product_input.model_dump(exclude_none=True)
        response = connect_olo_order_hub(
            http_method=HttpMethod.POST,
            bearer_token=olo_token,
            api_function=f"/v1.1/baskets/{basket_id}/products/batch",
            query_params=None,
            payload=request_body,
        )
    except Exception as e:
        raise Exception(
            f"[OloTool._apis.add_items_to_basket] Error while calling Olo API: {str(e)}"
        ) from e

    if response.status == 200:
        response_json = json.loads(response.decoded_body)

        # Validate the basket object
        response_json["basket"] = OloBasket.model_validate(response_json["basket"])

        return response_json
    else:
        logger.error(
            f"Failed to add items to basket with status {response.status}: {response.decoded_body}"
        )
        raise ValueError(
            f"Failed to add items to basket with status {response.status}: {response.decoded_body}"
        )


def set_basket_handoff_mode(
    basket_id: str, olo_token: OloAccessToken, handoff_mode: OloBasketHandoffMode
) -> OloBasket:
    """
    Sets the handoff mode for a basket.

    Args:
        basket_id (str): The basket ID
        olo_token (OloAccessToken): The Olo access token
        handoff_mode (OloBasketHandoffMode): The handoff mode

    Returns:
        OloBasket: A validated basket object from the API response
    """
    try:
        request_body = {
            "deliverymode": handoff_mode,
        }
        response = connect_olo_order_hub(
            http_method=HttpMethod.PUT,
            bearer_token=olo_token,
            api_function=f"/v1.1/baskets/{basket_id}/deliverymode",
            query_params=None,
            payload=request_body,
        )
    except Exception as e:
        raise Exception(
            f"[OloTool._apis.set_basket_handoff_mode] Error while calling Olo API: {str(e)}"
        ) from e

    if response.status == 200:
        return OloBasket.model_validate_json(response.decoded_body)
    else:
        logger.error(
            f"Failed to set basket handoff mode with status {response.status}: {response.decoded_body}"
        )
        raise ValueError(
            f"Failed to set basket handoff mode with status {response.status}: {response.decoded_body}"
        )


def validate_basket(basket_id: str, olo_token: OloAccessToken) -> ValidatedBasketTotals:
    """
    Validates a basket.

    Args:
        basket_id (str): The basket ID
        olo_token (OloAccessToken): The Olo access token

    Returns:
        ValidatedBasketTotals: A validated basket totals object from the API response
    """
    try:
        response = connect_olo_order_hub(
            http_method=HttpMethod.POST,
            bearer_token=olo_token,
            api_function=f"/v1.1/baskets/{basket_id}/validate",
        )
    except Exception as e:
        raise Exception(
            f"[OloTool._apis.validate_basket] Error while calling Olo API: {str(e)}"
        ) from e

    if response.status == 200:
        return ValidatedBasketTotals.model_validate_json(response.decoded_body)
    else:
        logger.error(
            f"Failed to validate basket with status {response.status}: {response.decoded_body}"
        )
        raise ValueError(
            f"Failed to validate basket with status {response.status}: {response.decoded_body}"
        )


def get_order_status(
    order_id: str, olo_token: OloAccessToken
) -> OloOrderSubmissionResponse:
    """
    Get the status of an order.

    Args:
        order_id (str): The order ID
        olo_token (OloAccessToken): The Olo access token

    Returns:
        OloOrderSubmissionResponse: A validated order response object from the API response. See the `OloOrderSubmissionResponse.status` field for the order status.
    """
    try:
        response = connect_olo_order_hub(
            http_method=HttpMethod.GET,
            bearer_token=olo_token,
            api_function=f"/v1.1/orders/{order_id}",
            query_params=None,
            payload=None,
        )
    except Exception as e:
        raise Exception(
            f"[OloTool._apis.get_order_status] Error while calling Olo API: {str(e)}"
        ) from e

    if response.status == 200:
        return OloOrderSubmissionResponse.model_validate_json(response.decoded_body)
    else:
        logger.error(
            f"Failed to get order status with status {response.status}: {response.decoded_body}"
        )
        raise ValueError(
            f"Failed to get order status with status {response.status}: {response.decoded_body}"
        )


def request_ccsf_token(
    basket_id: str, olo_token: OloAccessToken, auth_token: Optional[str] = None
) -> OloCCSFToken:
    """
    Requests a CCSF token for a given basket ID.

    Args:
        basket_id (str): The basket ID
        olo_token (OloAccessToken): The Olo access token
        auth_token (Optional[str], optional): The auth token used to identify the user. Defaults to None.
    Returns:
        OloCCSFToken: A validated CCSF token object from the API response
    """
    try:
        request_body = {
            "authtoken": auth_token,
        }

        response = connect_olo_order_hub(
            http_method=HttpMethod.POST,
            bearer_token=olo_token,
            api_function=f"/v1.1/baskets/{basket_id}/checkout",
            query_params=None,
            payload=request_body,
        )
    except Exception as e:
        raise Exception(
            f"[OloTool._apis.request_ccsf_token] Error while calling Olo API: {str(e)}"
        ) from e

    if response.status == 200:
        return OloCCSFToken.model_validate_json(response.decoded_body)
    else:
        logger.error(
            f"Failed to request CCSF token with status {response.status}: {response.decoded_body}"
        )
        raise ValueError(
            f"Failed to request CCSF token with status {response.status}: {response.decoded_body}"
        )


def submit_order(
    basket_id: str,
    olo_token: OloAccessToken,
    olo_order_submission_body: OloOrderSubmissionBody,
) -> OloOrderSubmissionResponse:
    """
    Submits an order for a given basket ID.

    Args:
        basket_id (str): The basket ID
        olo_order_submission_body (OloOrderSubmissionBody): The order submission body

    Returns:
        OloOrderSubmissionResponse: A validated order submission response object from the API response
    """
    try:
        response = connect_olo_order_hub(
            http_method=HttpMethod.POST,
            bearer_token=olo_token,
            api_function=f"/v1.1/baskets/{basket_id}/submit",
            query_params=None,
            payload=olo_order_submission_body.model_dump(exclude_none=True),
        )
    except Exception as e:
        raise Exception(
            f"[OloTool._apis.submit_order] Error while calling Olo API: {str(e)}"
        ) from e

    if response.status == 200:
        return OloOrderSubmissionResponse.model_validate_json(response.decoded_body)
    else:
        logger.error(
            f"Failed to submit order with status {response.status}: {response.decoded_body}"
        )
        raise ValueError(
            f"Failed to submit order with status {response.status}: {response.decoded_body}"
        )


def get_billing_schemes_info(
    basket_id: str, olo_token: OloAccessToken
) -> list[BillingScheme]:
    """
    Get the billing schemes info for a specified basket's restaurant.

    Args:
        basket_id (str): The basket ID
        olo_token (OloAccessToken): The Olo access token

    Returns:
        list[BillingScheme]: A list of BillingScheme objects containing the `id` and the `type` of the billing scheme
    """
    try:
        response = connect_olo_order_hub(
            http_method=HttpMethod.GET,
            bearer_token=olo_token,
            api_function=f"/v1.1/baskets/{basket_id}/billingschemes",
        )
    except Exception as e:
        raise Exception(
            f"[OloTool._apis.get_billing_schemes_info] Error while calling Olo API: {str(e)}"
        ) from e

    if response.status == 200:
        return [
            BillingScheme.model_validate(billing_scheme)
            for billing_scheme in json.loads(response.decoded_body).get(
                "billingschemes", []
            )
        ]
    else:
        logger.error(
            f"Failed to get billing schemes info with status {response.status}: {response.decoded_body}"
        )
        raise ValueError(
            f"Failed to get billing schemes info with status {response.status}: {response.decoded_body}"
        )
