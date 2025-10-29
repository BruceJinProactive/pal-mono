import json
from typing import Optional

from tools.olo_tool._apis._utils import (
    connect_olo_order_hub,
    connect_olo_order_hub_signed_requests,
    handle_olo_response,
)
from tools.olo_tool.classes import (
    Address,
    BillingScheme,
    DeliveryAddressValidationResponse,
    OloAccessToken,
    OloBasket,
    OloBasketHandoffMode,
    OloCCSFToken,
    OloOrderSubmissionBody,
    OloOrderSubmissionResponse,
    OloProductInput,
    OloSignedToken,
    OloStore,
    ValidatedBasketTotals,
)
from tools.utils.ordering.classes import HttpMethod


def _connect_olo_api_auto(
    http_method: HttpMethod,
    olo_token: OloAccessToken | OloSignedToken,
    api_function: str,
    query_params: dict | None = None,
    extra_headers: dict | None = None,
    payload: dict | str | None = None,
    forwarded_ip: str | None = None,
    base_url: str | None = None,
):
    """
    Automatically choose the appropriate connection method based on token type.

    Args:
        forwarded_ip: Optional IP address for X-Forwarded-For header
        base_url: Optional custom API endpoint
    """
    if isinstance(olo_token, OloSignedToken):
        return connect_olo_order_hub_signed_requests(
            http_method=http_method,
            signed_token=olo_token,
            api_function=api_function,
            query_params=query_params,
            extra_headers=extra_headers,
            payload=payload,
            forwarded_ip=forwarded_ip,
            base_url=base_url,
        )
    else:
        return connect_olo_order_hub(
            http_method=http_method,
            bearer_token=olo_token,
            api_function=api_function,
            query_params=query_params,
            extra_headers=extra_headers,
            payload=payload,
            forwarded_ip=forwarded_ip,
            general_api_endpoint=base_url,
        )


def get_store_info(
    restaurant_id: int,
    olo_token: OloAccessToken | OloSignedToken,
    forwarded_ip: str | None = None,
    base_url: str | None = None,
) -> OloStore:
    """
    Get the store info for a given restaurant ID

    Args:
        restaurant_id (int): The restaurant ID
        olo_token (OloAccessToken | OloSignedToken): The Olo access token or signed token
        forwarded_ip: Optional IP address for X-Forwarded-For header

    Returns:
        OloStore: A validated store object from the API response
    """
    try:
        response = _connect_olo_api_auto(
            http_method=HttpMethod.GET,
            olo_token=olo_token,
            api_function=f"/v1.1/restaurants/{restaurant_id}",
            query_params=None,
            payload=None,
            forwarded_ip=forwarded_ip,
            base_url=base_url,
        )
        result = handle_olo_response(response, OloStore)
        if not isinstance(result, OloStore):
            raise ValueError(f"Expected OloStore but got {type(result)}")
        return result
    except Exception as e:
        raise ValueError(
            f"Failed to get store info for restaurant {restaurant_id}: {str(e)}"
        ) from e


def get_online_ordering_status(
    restaurant_id: int,
    olo_token: OloAccessToken | OloSignedToken,
    forwarded_ip: str | None = None,
    base_url: str | None = None,
) -> int | str:
    """
    Get the online ordering status for ONE given restaurant ID

    Args:
        restaurant_id (int): The restaurant ID
        olo_token (OloAccessToken): The Olo access token
        forwarded_ip: Optional IP address for X-Forwarded-For header

    Returns:
        int | str: Current estimated ASAP order lead time in minutes. If leadtime is not found, return a string indicating the restaurant is closed or not accepting online orders.
    """
    try:
        request_body = {
            "vendorids": [restaurant_id],
        }
        response = _connect_olo_api_auto(
            http_method=HttpMethod.POST,
            olo_token=olo_token,
            api_function="/v1.1/restaurants/capacity/leadtimes",
            query_params=None,
            payload=request_body,
            forwarded_ip=forwarded_ip,
            base_url=base_url,
        )

        response_json = json.loads(handle_olo_response(response))
        if (
            response_json["leadtimes"][0]["totalminutes"] is not None
        ):  # Explicitly check for None to avoid 0 leadtime being returned
            return response_json["leadtimes"][0]["totalminutes"]
        else:
            # If no leadtime data is found, we need to check if the restaurant is open and accepting online orders
            store_info = get_store_info(
                restaurant_id, olo_token, forwarded_ip=forwarded_ip, base_url=base_url
            )
            if store_info.isavailable:
                return "The restaurant is accepting online orders. The estimated ASAP order lead time is 0 minutes."
            elif store_info.iscurrentlyopen:
                return (
                    "The restaurant is currently open but not accepting online orders."
                )
            else:
                return "The restaurant closed and not accepting online orders."

    except Exception as e:
        raise ValueError(
            f"Failed to get online ordering status for restaurant {restaurant_id}: {str(e)}"
        ) from e


def validate_address(
    restaurant_id: int,
    address: Address,
    olo_token: OloAccessToken | OloSignedToken,
    forwarded_ip: str | None = None,
    base_url: str | None = None,
) -> DeliveryAddressValidationResponse:
    """
    Validates an address for a given restaurant ID.

    Args:
        restaurant_id (int): The restaurant ID
        address (Address): The address to validate
        olo_token (OloAccessToken | OloSignedToken): The Olo access token or signed token
        forwarded_ip: Optional IP address for X-Forwarded-For header

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
        response = _connect_olo_api_auto(
            http_method=HttpMethod.POST,
            olo_token=olo_token,
            api_function=f"/v1.1/restaurants/{restaurant_id}/checkdeliverycoverage",
            query_params=None,
            payload=request_body,
            forwarded_ip=forwarded_ip,
            base_url=base_url,
        )
        result = handle_olo_response(response, DeliveryAddressValidationResponse)
        if not isinstance(result, DeliveryAddressValidationResponse):
            raise ValueError(
                f"Expected DeliveryAddressValidationResponse but got {type(result)}"
            )
        return result
    except Exception as e:
        raise ValueError(
            f"Failed to validate address for restaurant {restaurant_id}: {str(e)}"
        ) from e


def create_basket(
    restaurant_id: int,
    olo_token: OloAccessToken | OloSignedToken,
    auth_token: Optional[str] = None,
    forwarded_ip: str | None = None,
    base_url: str | None = None,
) -> OloBasket:
    """
    Creates a basket for a restaurant.

    Args:
        restaurant_id (int): The restaurant ID
        olo_token (OloAccessToken): The Olo access token
        auth_token (Optional[str], optional): The auth token. Defaults to None.
        forwarded_ip: Optional IP address for X-Forwarded-For header

    Returns:
        OloBasket: A validated basket object from the API response
    """
    try:
        request_body = {
            "vendorid": restaurant_id,
            "authtoken": auth_token,
        }
        response = _connect_olo_api_auto(
            http_method=HttpMethod.POST,
            olo_token=olo_token,
            api_function="/v1.1/baskets/create",
            query_params=None,
            payload=request_body,
            forwarded_ip=forwarded_ip,
            base_url=base_url,
        )
        result = handle_olo_response(response, OloBasket)
        if not isinstance(result, OloBasket):
            raise ValueError(f"Expected OloBasket but got {type(result)}")
        return result
    except Exception as e:
        raise ValueError(
            f"Failed to create basket for restaurant {restaurant_id}: {str(e)}"
        ) from e


def add_items_to_basket(
    basket_id: str,
    olo_token: OloAccessToken | OloSignedToken,
    olo_product_input: OloProductInput,
    forwarded_ip: str | None = None,
    base_url: str | None = None,
) -> dict:
    """
    Adds items to a basket.

    Args:
        basket_id (str): The basket ID
        olo_token (OloAccessToken): The Olo access token
        olo_product_input (OloProductInput): The Olo product input
        forwarded_ip: Optional IP address for X-Forwarded-For header

    Returns:
        dict: A dictionary containing the new basket (OloBasket) and a list of errors
    """
    try:
        request_body = olo_product_input.model_dump(
            exclude_none=True,
        )
        response = _connect_olo_api_auto(
            http_method=HttpMethod.POST,
            olo_token=olo_token,
            api_function=f"/v1.1/baskets/{basket_id}/products/batch",
            query_params=None,
            payload=request_body,
            forwarded_ip=forwarded_ip,
            base_url=base_url,
        )
        response_json = json.loads(handle_olo_response(response))
        response_json["basket"] = OloBasket.model_validate(response_json["basket"])

        # Check for errors
        if response_json.get("errors") and len(response_json["errors"]) > 0:
            raise ValueError(
                f"Failed to add items to basket {basket_id}: {response_json['errors']}"
            )

        return response_json
    except Exception as e:
        raise ValueError(f"Failed to add items to basket {basket_id}: {str(e)}") from e


def set_basket_handoff_mode(
    basket_id: str,
    olo_token: OloAccessToken | OloSignedToken,
    handoff_mode: OloBasketHandoffMode,
    forwarded_ip: str | None = None,
    base_url: str | None = None,
) -> OloBasket:
    """
    Sets the handoff mode for a basket.

    Args:
        basket_id (str): The basket ID
        olo_token (OloAccessToken): The Olo access token
        handoff_mode (OloBasketHandoffMode): The handoff mode
        forwarded_ip: Optional IP address for X-Forwarded-For header

    Returns:
        OloBasket: A validated basket object from the API response
    """
    try:
        request_body = {
            "deliverymode": handoff_mode.value,
        }
        response = _connect_olo_api_auto(
            http_method=HttpMethod.PUT,
            olo_token=olo_token,
            api_function=f"/v1.1/baskets/{basket_id}/deliverymode",
            query_params=None,
            payload=request_body,
            forwarded_ip=forwarded_ip,
            base_url=base_url,
        )
        result = handle_olo_response(response, OloBasket)
        if not isinstance(result, OloBasket):
            raise ValueError(f"Expected OloBasket but got {type(result)}")
        return result
    except Exception as e:
        raise ValueError(
            f"Failed to set basket handoff mode for basket {basket_id}: {str(e)}"
        ) from e


def validate_basket(
    basket_id: str,
    olo_token: OloAccessToken | OloSignedToken,
    forwarded_ip: str | None = None,
    base_url: str | None = None,
) -> ValidatedBasketTotals:
    """
    Validates a basket.

    Args:
        basket_id (str): The basket ID
        olo_token (OloAccessToken): The Olo access token
        forwarded_ip: Optional IP address for X-Forwarded-For header

    Returns:
        ValidatedBasketTotals: A validated basket totals object from the API response

    """
    try:
        response = _connect_olo_api_auto(
            http_method=HttpMethod.POST,
            olo_token=olo_token,
            api_function=f"/v1.1/baskets/{basket_id}/validate",
            forwarded_ip=forwarded_ip,
            base_url=base_url,
        )
        result = handle_olo_response(response, ValidatedBasketTotals)
        if not isinstance(result, ValidatedBasketTotals):
            raise ValueError(f"Expected ValidatedBasketTotals but got {type(result)}")
        return result
    except Exception as e:
        raise ValueError(f"Failed to validate basket {basket_id}: {str(e)}") from e


def get_order_status(
    order_id: str,
    olo_token: OloAccessToken,
    forwarded_ip: str | None = None,
) -> OloOrderSubmissionResponse:
    """
    Get the status of an order.

    Args:
        order_id (str): The order ID
        olo_token (OloAccessToken): The Olo access token
        forwarded_ip: Optional IP address for X-Forwarded-For header

    Returns:
        OloOrderSubmissionResponse: A validated order response object from the API response
    """
    try:
        response = _connect_olo_api_auto(
            http_method=HttpMethod.GET,
            olo_token=olo_token,
            api_function=f"/v1.1/orders/{order_id}",
            query_params=None,
            payload=None,
            forwarded_ip=forwarded_ip,
        )
        result = handle_olo_response(response, OloOrderSubmissionResponse)
        if not isinstance(result, OloOrderSubmissionResponse):
            raise ValueError(
                f"Expected OloOrderSubmissionResponse but got {type(result)}"
            )
        return result
    except Exception as e:
        raise ValueError(
            f"Failed to get order status for order {order_id}: {str(e)}"
        ) from e


def request_ccsf_token(
    basket_id: str,
    olo_token: OloAccessToken | OloSignedToken,
    auth_token: Optional[str] = None,
    forwarded_ip: str | None = None,
    base_url: str | None = None,
) -> OloCCSFToken:
    """
    Requests a CCSF token for a given basket ID.

    Args:
        basket_id (str): The basket ID
        olo_token (OloAccessToken): The Olo access token
        auth_token (Optional[str], optional): The auth token used to identify the user. Defaults to None.
        forwarded_ip: Optional IP address for X-Forwarded-For header

    Returns:
        OloCCSFToken: A validated CCSF token object from the API response
    """
    try:
        request_body = {
            "authtoken": auth_token,
        }

        response = _connect_olo_api_auto(
            http_method=HttpMethod.POST,
            olo_token=olo_token,
            api_function=f"/v1.1/baskets/{basket_id}/checkout",
            query_params=None,
            payload=request_body,
            forwarded_ip=forwarded_ip,
            base_url=base_url,
        )
        result = handle_olo_response(response, OloCCSFToken)
        if not isinstance(result, OloCCSFToken):
            raise ValueError(f"Expected OloCCSFToken but got {type(result)}")
        return result
    except Exception as e:
        raise ValueError(
            f"Failed to request CCSF token for basket {basket_id}: {str(e)}"
        ) from e


def submit_order(
    basket_id: str,
    olo_token: OloAccessToken | OloSignedToken,
    olo_order_submission_body: OloOrderSubmissionBody,
    forwarded_ip: str | None = None,
    base_url: str | None = None,
) -> OloOrderSubmissionResponse:
    """
    Submits an order for a given basket ID.

    Args:
        basket_id (str): The basket ID
        olo_token (OloAccessToken): The Olo access token
        olo_order_submission_body (OloOrderSubmissionBody): The order submission body
        forwarded_ip: Optional IP address for X-Forwarded-For header

    Returns:
        OloOrderSubmissionResponse: A validated order submission response object from the API response
    """
    try:
        response = _connect_olo_api_auto(
            http_method=HttpMethod.POST,
            olo_token=olo_token,
            api_function=f"/v1.1/baskets/{basket_id}/submit",
            query_params=None,
            payload=olo_order_submission_body.model_dump(exclude_none=True),
            forwarded_ip=forwarded_ip,
            base_url=base_url,
        )
        result = handle_olo_response(response, OloOrderSubmissionResponse)
        if not isinstance(result, OloOrderSubmissionResponse):
            raise ValueError(
                f"Expected OloOrderSubmissionResponse but got {type(result)}"
            )
        return result
    except Exception as e:
        raise ValueError(
            f"Failed to submit order for basket {basket_id}: {str(e)}"
        ) from e


def get_billing_schemes_info(
    basket_id: str,
    olo_token: OloAccessToken | OloSignedToken,
    forwarded_ip: str | None = None,
    base_url: str | None = None,
) -> list[BillingScheme]:
    """
    Get the billing schemes info for a specified basket's restaurant.

    Args:
        basket_id (str): The basket ID
        olo_token (OloAccessToken): The Olo access token
        forwarded_ip: Optional IP address for X-Forwarded-For header

    Returns:
        list[BillingScheme]: A list of BillingScheme objects containing the `id` and the `type` of the billing scheme
    """
    try:
        response = _connect_olo_api_auto(
            http_method=HttpMethod.GET,
            olo_token=olo_token,
            api_function=f"/v1.1/baskets/{basket_id}/billingschemes",
            forwarded_ip=forwarded_ip,
            base_url=base_url,
        )
        response_json = json.loads(handle_olo_response(response))
        return [
            BillingScheme.model_validate(billing_scheme)
            for billing_scheme in response_json.get("billingschemes", [])
        ]
    except Exception as e:
        raise ValueError(
            f"Failed to get billing schemes info for basket {basket_id}: {str(e)}"
        ) from e
