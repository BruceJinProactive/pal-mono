import http.client
import json
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from os import getenv
from typing import Optional, Tuple, Type, TypeVar

from pydantic import BaseModel, ValidationError

from ai.tools.adapters.integrations.data_models.access_token import AccessToken


@dataclass
class AdoraApiKeyAndSecret:
    api_key: str
    api_secret: str


_adora_key_and_secret = None
_adora_api_key = getenv("ADORA_POS_API_KEY")
_adora_api_secret = getenv("ADORA_POS_API_SECRET")
if _adora_api_key and _adora_api_secret:
    _adora_key_and_secret = AdoraApiKeyAndSecret(
        api_key=_adora_api_key,
        api_secret=_adora_api_secret,
    )


class AdoraCustomerInfo(BaseModel):
    """
    NOTE: phone number must be in (xxx)xxx-xxxx format
    NOTE: Placing order will send a text to the phone number
    """

    first_name: str
    last_name: str
    phone_number: str  # NOTE: phone number must be in (xxx)xxx-xxxx format
    email: str


class AdoraPosOrderType(str, Enum):
    Delivery = "Delivery"
    TakeOut = "TakeOut"


class AdoraPosOrderCalculationResult(BaseModel):
    # Key is used on the Adora Pos API side in subsequent API calls to refer to the order. Ignore it outside of this file
    Key: str
    IsPaymentRequired: bool
    SubTotal: float
    Total: float
    Discount: float
    TaxAmount: float
    ServiceCharge: float
    DeliveryCharge: float


class AdoraPosDeliveryAddress(BaseModel):
    address: str
    extendedAddress: str = (
        ""  # Required by Adora API, used for Apt/Suite number, can be empty string
    )
    city: str
    state: str
    zip: str
    lat: float = 37.230727  # TODO: get this from an address to lat long API
    lng: float = -121.953576  # TODO: get this from an address to lat long API
    instruction: str = ""  # Required by Adora API but can be empty string
    typeId: int = 1  # TODO: get this from address validation API
    extraField1: str = (
        ""  # Required by Adora API but not sure its use and can be empty string
    )
    extraField2: str = (
        ""  # Required by Adora API but not sure its use and can be empty string
    )


def get_adora_pos_store_menu(store_id: str, log_request: bool = False) -> Optional[str]:
    """returns json string of the store menu"""

    if _adora_key_and_secret:
        bearer_token = _get_adora_pos_auth_token(_adora_key_and_secret)
        if bearer_token:
            return _get_adora_pos_store_menu(store_id, bearer_token, log_request)

    return None


def get_adora_pos_consumer_account_info(
    store_id: str,
    consumer_phone_number: str,
    log_request: bool = False,
) -> Optional[str]:
    """returns json string of the consumer account info"""

    if _adora_key_and_secret:
        bearer_token = _get_adora_pos_auth_token(_adora_key_and_secret)
        if bearer_token:
            return _get_adora_pos_consumer_account_info(
                bearer_token, store_id, consumer_phone_number, log_request
            )

    return None


def calculate_tax_fees_and_total(
    store_id: str,
    order_items: list[dict],
    log_request: bool = False,
) -> Optional[AdoraPosOrderCalculationResult]:
    """Calls Adora API to validates order_items and calculate subtotal and total.
    Returns AdoraPosOrderCalculationResult object which contains order amount calculations,
    including subtotal, taxes, fees, and total
    """

    if _adora_key_and_secret:
        bearer_token = _get_adora_pos_auth_token(_adora_key_and_secret)
        if bearer_token:
            # use place holder user info for calculating fees
            # Adora API won't work if we are missing User Info.
            customer: AdoraCustomerInfo = AdoraCustomerInfo(
                first_name="Agent",
                last_name="Smith",
                phone_number="(888)123-4567",
                email="GKvzQ@example.com",
            )

            return _validate_order(
                bearer_token, store_id, customer, order_items, log_request=log_request
            )

    return None


def submit_order_and_text_payment_link(
    store_id: str,
    customer: AdoraCustomerInfo,
    order_items: list[dict],
    order_type: AdoraPosOrderType = AdoraPosOrderType.TakeOut,
    delivery_address: Optional[AdoraPosDeliveryAddress] = None,
    log_request: bool = False,
) -> Optional[AdoraPosOrderCalculationResult]:
    """Calls (multiple) Adora APIs to validates order_items and calculate subtotal and total; submit order
    and sent text payment link to the consumer.
    Returns AdoraPosOrderCalculationResult object which contains order amount calculations,
    including subtotal, taxes, fees, and total
    """

    if _adora_key_and_secret:
        bearer_token = _get_adora_pos_auth_token(_adora_key_and_secret)
        if bearer_token:

            order_calculation_result = _validate_order(
                bearer_token,
                store_id,
                customer,
                order_items,
                order_type=order_type,
                delivery_address=delivery_address,
                log_request=log_request,
            )
            if order_calculation_result:

                order_save_result = _save_order(
                    bearer_token, order_calculation_result.Key, log_request=log_request
                )
                if order_save_result and order_save_result.Success == 1:
                    if log_request:
                        print("Order saved: " + str(order_save_result.OrderID))

                    # NOTE: HACK: sleep for 3 seconds to wait for OrderID to propagate through Adora POS systems
                    # otherwise the Adora APIs might not be able to find the order ID if we send it too fast
                    # TODO: find a better solution for this by asking the Adora eng team
                    time.sleep(3)

                    (send_payment_link_success, send_payment_link_response) = (
                        _send_payment_link(
                            bearer_token,
                            store_id,
                            order_save_result.OrderID,
                            customer.phone_number,
                            log_request=log_request,
                        )
                    )
                    if send_payment_link_success:
                        # return the order calculation details to the caller if order was placed successfully
                        return order_calculation_result

    return None


# Define a generic type variable for a subclass of BaseModel
T = TypeVar("T", bound=BaseModel)


def _parse_json(model_class: Type[T], json_str: str) -> Optional[T]:
    """Try to parse the JSON string into the model class. If it fails, print the error and return None."""

    try:
        data_model = model_class.model_validate_json(json_str)
        return data_model
    except ValidationError as e:
        print(e)

    return None


class AdoraApiHttpMethod(str, Enum):
    GET = "GET"
    POST = "POST"


class AdoraPosOrderHubResponse(BaseModel):
    status: int
    reason: str
    decoded_body: str


def _get_adora_pos_auth_token(
    api_key_and_secret: AdoraApiKeyAndSecret,
) -> Optional[AccessToken]:
    """
    Returns a bearer token. It expires in 1 hour.
    Each public API in this file will get a new token from Adora to keep it simple and Pure Functional
    """
    payload = (
        "grant_type=client_credentials&client_id="
        + api_key_and_secret.api_key
        + "&client_secret="
        + api_key_and_secret.api_secret
    )
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    conn = http.client.HTTPSConnection("identity.adorapos.net")
    conn.request("POST", "/connect/token", payload, headers)
    res = conn.getresponse()
    data = res.read()
    bearer_token_json = data.decode("utf-8")

    return _parse_json(AccessToken, bearer_token_json)


# TODO: After setting up dependency injection, use a Logger and a LoggerAdapter, and inject it as a dependency
# TODO: Log HTTP errors to Monitoring
def _connect_adora_order_hub(
    http_method: AdoraApiHttpMethod,
    auth_token: AccessToken,
    api_function: str,
    query_params: Optional[dict] = None,
    extra_headers: Optional[dict] = None,
    payload: Optional[str] = None,
    log_request: bool = False,
) -> AdoraPosOrderHubResponse:
    """utility function to connect to Adora Order Hub API"""

    conn = http.client.HTTPSConnection("public.api.adorapos.net")
    headers = {
        "Content-Type": "application/json",
        "Authorization": auth_token.get_token_header_value(),
    }
    if extra_headers:
        headers.update(extra_headers)

    path_plus_params = "/api/v1/OrderHub/" + api_function

    if query_params:
        path_plus_params = path_plus_params + "?" + urllib.parse.urlencode(query_params)

    if http_method == AdoraApiHttpMethod.GET:
        conn.request("GET", path_plus_params, payload, headers)
    elif http_method == AdoraApiHttpMethod.POST:
        conn.request("POST", path_plus_params, payload, headers)
    else:
        assert False, "Invalid HTTP method for Adora Pos API"

    res = conn.getresponse()
    data = res.read()
    response_body = data.decode("utf-8")
    if log_request:
        print("request: " + path_plus_params + "\n")
        print("query_params: " + str(query_params) + "\n")
        print("headers: " + str(headers) + "\n")
        print("payload: " + str(payload) + "\n")
        print(res.status, res.reason)
        print("response_body: " + response_body + "\n")

    order_hub_response = AdoraPosOrderHubResponse(
        status=res.status, reason=res.reason, decoded_body=response_body
    )
    return order_hub_response


def _get_adora_pos_store_menu(
    store_id: str, bearer_token: AccessToken, log_request: bool = False
) -> Optional[str]:
    """gets json string of the store menu
    maps to Adora API doc: https://adoraimages.blob.core.windows.net/api-docs/orderhubapi.html#tag/OrderHub/paths/~1api~1v%7Bversion%7D~1OrderHub~1menu/get
    """

    response = _connect_adora_order_hub(
        AdoraApiHttpMethod.GET,
        bearer_token,
        "menu",
        query_params={"sid": store_id},
        extra_headers=None,
        payload=None,
        log_request=log_request,
    )
    if response.status == 200:
        return response.decoded_body
    else:
        return None


def _get_adora_pos_consumer_account_info(
    bearer_token: AccessToken,
    store_id: str,
    consumer_phone_number: str,
    log_request: bool = False,
) -> Optional[str]:
    """gets json string of the consumer account info
    maps to Adora API doc: https://adoraimages.blob.core.windows.net/api-docs/orderhubapi.html#tag/OrderHub/paths/~1api~1v%7Bversion%7D~1OrderHub~1customer/get
    """

    response = _connect_adora_order_hub(
        AdoraApiHttpMethod.GET,
        bearer_token,
        "customer",
        query_params={"sid": store_id, "phone": consumer_phone_number},
        extra_headers=None,
        payload=None,
        log_request=log_request,
    )
    if response.status == 200:
        return response.decoded_body
    else:
        return None


def _validate_order(
    bearer_token: AccessToken,
    store_id: str,
    customer: AdoraCustomerInfo,
    order_items: list[dict],
    order_type: AdoraPosOrderType = AdoraPosOrderType.TakeOut,
    delivery_address: Optional[AdoraPosDeliveryAddress] = None,
    log_request: bool = False,
) -> Optional[AdoraPosOrderCalculationResult]:
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
    # TODO attach property to enum value instead
    assert order_type == AdoraPosOrderType.TakeOut or (
        order_type == AdoraPosOrderType.Delivery and delivery_address
    ), "Invalid order type, either takeout or need address for delivery"

    # TODO: validate address
    order_type_string = (
        "Delivery"
        if (order_type == AdoraPosOrderType.Delivery and delivery_address)
        else "TakeOut"
    )

    # NOTE: Adoro API says "promiseDateTime" is optional, but it's actually required, and it's required to be
    # less than 24 hours (or 12 hours, need trial and error testing) in the future. Need to check with their Eng to figure out why.
    # In the mean time, we just create a datatime that's 2 hour in the future to satify Adora Pos API requirement.
    current_datetime = datetime.now(timezone.utc)
    future_datetime = current_datetime + timedelta(hours=2)
    formatted_datetime = future_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")

    item_list = []
    for order_item in order_items:
        item_list.append({"group": [order_item]})

    payload_dict = {
        "storeId": store_id,
        "couponId": 0,
        "orderType": order_type_string,
        "orderTypeSubType": "OverCounter",
        "promiseDateTime": formatted_datetime,
        "customer": {
            "name": customer.first_name,
            "lastname": customer.last_name,
            "phone": customer.phone_number,
            "email": customer.email,
        },
        "items": item_list,
        "discount": 0,
        "paid": False,
        "orderComment": " ",
    }

    # add delivery address
    if order_type == AdoraPosOrderType.Delivery and delivery_address:
        delivery_address_dict = delivery_address.model_dump()
        payload_dict["deliveryAddress"] = delivery_address_dict

    payload = json.dumps(payload_dict)

    response = _connect_adora_order_hub(
        AdoraApiHttpMethod.POST,
        bearer_token,
        "validateOrder",
        query_params=None,
        extra_headers=None,
        payload=payload,
        log_request=log_request,
    )
    if response.status == 200:
        return _parse_json(AdoraPosOrderCalculationResult, response.decoded_body)
    else:
        return None


class _AdoraPosSaveOrderResult(BaseModel):
    Success: int
    OrderID: int
    OrderNo: int
    CustomerID: int
    AddressID: int
    ProfileID: int
    msg: str
    ProfUpdated: int


def _save_order(
    bearer_token: AccessToken,
    order_validation_key: str,
    log_request: bool = False,
) -> Optional[_AdoraPosSaveOrderResult]:
    """
    returns order save result
    maps to Adora API doc: https://adoraimages.blob.core.windows.net/api-docs/orderhubapi.html#tag/OrderHub/paths/~1api~1v%7Bversion%7D~1OrderHub~1save/post
    example success return value with http status 200::
    {
        "Success": 1,
        "OrderID": 104721668,
        "OrderNo": 101,
        "CustomerID": 135029,
        "AddressID": 79776,
        "ProfileID": 0,
        "msg": "",
        "ProfUpdated": 1
    }
    """

    extra_headers = {
        "orderKey": order_validation_key,
    }
    response = _connect_adora_order_hub(
        AdoraApiHttpMethod.POST,
        bearer_token,
        "save",
        query_params=None,
        extra_headers=extra_headers,
        payload=None,
        log_request=log_request,
    )
    if response.status == 200:
        return _parse_json(_AdoraPosSaveOrderResult, response.decoded_body)
    else:
        return None


def _send_payment_link(
    bearer_token: AccessToken,
    store_id: str,
    order_id: int,
    consumer_phone_number: str,
    log_request: bool = False,
) -> Tuple[bool, str]:
    """
    text payment link to the user's phone number
    maps to Adora API doc: https://adoraimages.blob.core.windows.net/api-docs/orderhubapi.html#tag/OrderHub/paths/~1api~1v%7Bversion%7D~1OrderHub~1textPaymentUrl/post
    Adora returns an UUID when this call is successful, which might be an ID from their payment processor. need to confirm with Adora on how to use this.
    example success return value with http status 200:
    de5bbde1-bc09-4f5f-a365-34223c4bd53e
    """

    payload = json.dumps(
        {
            "orderId": order_id,
            "storeId": store_id,
            "customerPhoneNo": consumer_phone_number,
        }
    )

    response = _connect_adora_order_hub(
        AdoraApiHttpMethod.POST,
        bearer_token,
        "textPaymentUrl",
        query_params=None,
        extra_headers=None,
        payload=payload,
        log_request=log_request,
    )
    return (response.status == 200, response.decoded_body)
