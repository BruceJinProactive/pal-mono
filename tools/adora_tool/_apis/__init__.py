import http.client
import json
from datetime import datetime

from tools.adora_tool.classes import (
    AdoraAccessToken,
    AdoraCustomerInfo,
    AdoraOrderCalculationResult,
    AdoraSavedOrderResult,
    AdoraValidatedAddress,
    AdoraValidatedAddressList,
    ValidateAddressPayload,
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


def _get_loyalty_status(customer_info: dict) -> bool:
    """
    Extract loyalty status from customer info.

    Args:
        customer_info: Dictionary containing customer information

    Returns:
        bool: True if customer is a loyalty member, False otherwise
    """
    is_loyalty_member = False

    if "loyaltyMember" in customer_info:
        is_loyalty_member = bool(customer_info["loyaltyMember"])

    return is_loyalty_member


def _get_reward_info(customer_info: dict) -> str:
    """
    Extract reward information from customer info.

    Args:
        customer_info: Dictionary containing customer information

    Returns:
        str: Formatted reward information
    """
    rewards_info = ""

    if "customerRewards" in customer_info and customer_info["customerRewards"]:
        rewards_info = "Customer Rewards:\n\n"
        for reward in customer_info["customerRewards"]:
            reward_date = reward.get("earnedDate", "")
            formatted_date = reward_date
            if reward_date:
                try:
                    date_obj = datetime.fromisoformat(
                        reward_date.replace("Z", "+00:00")
                    )
                    formatted_date = date_obj.strftime("%Y-%m-%d %H:%M:%S")
                except Exception as e:
                    logger.error(f"Error formatting reward date: {e}")
                    formatted_date = reward_date

            rewards_info += (
                f"Reward ID: {reward.get('rewardId', '')}\n"
                f"Earned Date: {formatted_date}\n"
                f"Coupon ID: {reward.get('couponId', '')}\n"
                f"Coupon Name: {reward.get('couponName', '')}\n"
                f"Reward Name: {reward.get('rewardName', '')}\n\n"
            )

    return rewards_info


def _get_offer_info(customer_info: dict) -> str:
    """
    Extract offer information from customer info.

    Args:
        customer_info: Dictionary containing customer information

    Returns:
        str: Formatted offer information
    """
    offers_info = ""

    if "customerOffers" in customer_info and customer_info["customerOffers"]:
        offers = customer_info["customerOffers"]
        offers_info = "Customer Offers:\n\n"

        # Extract codes
        if "codes" in offers and offers["codes"]:
            offers_info += "Campaign Codes:\n"
            for code in offers["codes"]:
                offers_info += f"{json.dumps(code, indent=2)}\n\n"

        # Extract coupons
        if "coupons" in offers and offers["coupons"]:
            offers_info += "Coupons:\n"
            for coupon in offers["coupons"]:
                offers_info += f"{json.dumps(coupon, indent=2)}\n\n"

    return offers_info


def _get_next_order_credits(customer_info: dict) -> str:
    """
    Extract next order credits information from customer info.

    Args:
        customer_info: Dictionary containing customer information

    Returns:
        str: Formatted next order credits information
    """
    credits_info = ""

    if (
        "customerNextOrderCredits" in customer_info
        and customer_info["customerNextOrderCredits"]
    ):
        credits = customer_info["customerNextOrderCredits"]
        credits_info = "Customer Next Order Credits:\n\n"

        for credit in credits:
            credits_info += (
                f"Credit ID: {credit.get('CreditId', '')}\n"
                f"Store Key: {credit.get('storeKey', '')}\n"
                f"Coupon ID: {credit.get('couponId', '')}\n"
                f"Discount: {credit.get('discount', '')}\n"
                f"Coupon Name: {credit.get('couponName', '')}\n"
                f"Coupon Description: {credit.get('couponDescription', '')}\n\n"
            )

    return credits_info


def _format_customer_info(customer_info: AdoraCustomerInfo) -> str:
    """
    Format AdoraCustomerInfo object into a concise string representation.

    Args:
        customer_info: AdoraCustomerInfo object containing customer information

    Returns:
        str: Formatted customer information as a string
    """
    info_dict = customer_info.model_dump()

    # Basic customer information
    formatted_info = (
        f"Customer: {info_dict.get('firstName', '')} {info_dict.get('lastName', '')}\n"
    )

    # Loyalty status
    formatted_info += (
        f"Loyalty Member: {'Yes' if _get_loyalty_status(info_dict) else 'No'}\n"
    )

    # Add reward information
    if rewards := info_dict.get("customerRewards", []):
        formatted_info += f"Rewards: {rewards}\n"

    # Add offer information
    if "customerOffers" in info_dict and info_dict["customerOffers"]:
        formatted_info += _get_offer_info(info_dict)

    # Add next order credits
    if info_dict.get("customerNextOrderCredits", []):
        formatted_info += _get_next_order_credits(info_dict)

    return formatted_info


def get_customer_info(
    bearer_token: AdoraAccessToken,
    store_id: str,
    phone_number: str,
    qa_store: bool,
    reformat: bool = True,
) -> str | AdoraCustomerInfo | None:
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

    if response.status == 200:
        customer_info = _utils.parse_json(AdoraCustomerInfo, response.decoded_body)
        if customer_info:
            return _format_customer_info(customer_info) if reformat else customer_info
        logger.debug(
            f"[AdoraTool._apis.get_customer_info] Error parsing customer info: {response.decoded_body}"
        )
        return None
    elif response.status == 404:
        # For 404 responses, parse the error message from the response
        error_info = json.loads(response.decoded_body)
        logger.debug(
            f"[AdoraTool._apis.get_customer_info] Customer not found: {error_info}"
        )
        error_message = error_info.get("message", "Customer not found.")
        return error_message + " Please double check your phone number and try again."
    else:
        logger.debug(
            f"[AdoraTool._apis.get_customer_info] Internal error {response.status}: {response.decoded_body}"
        )
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


def get_store_info(
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

    if response.status == 200:
        return response.decoded_body
    else:
        return None


def validate_order(
    bearer_token: AdoraAccessToken, payload: str, qa_store: bool
) -> AdoraOrderCalculationResult | None:
    logger.debug(f"[AdoraTool._apis.validate_order] Payload: {payload}")

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
    payload: ValidateAddressPayload,
    qa_store: bool,
) -> tuple[bool, list[AdoraValidatedAddress] | str]:
    """
    Validate an address (latitude + longitude) with Adora POS.

    Args:
        bearer_token (AccessToken): The bearer token to authenticate with Adora POS.
        payload (ValidateAddressPayload): The payload containing the address information.
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
        payload=json.dumps(payload.model_dump(by_alias=True, exclude_defaults=True)),
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


def validate_coupon_code(
    bearer_token: AdoraAccessToken,
    store_id: str,
    coupon_code: str,
    qa_store: bool,
    culture_code: str = "en-US",
) -> dict | None:
    """
    Validate a coupon code for a specific store.

    Args:
        bearer_token (AdoraAccessToken): The bearer token to authenticate with Adora POS.
        store_id (str): The ID of the store.
        coupon_code (str): The coupon code to validate.
        qa_store (bool): True if the QA environment should be used.
        culture_code (str, optional): The culture code. Defaults to "en-US".

    Returns:
        dict | None: A dictionary containing validation results if successful, None otherwise.
            The dictionary includes:
            - isValid (bool): Whether the coupon code is valid
            - message (str): Message about the validation result
            - couponId (int): ID of the coupon if valid
            - couponCode (str): The validated coupon code
            - description (str): Description of the coupon
    """
    response = _utils.connect_adora_order_hub(
        "GET",
        bearer_token,
        "validateCouponCode",
        query_params={
            "sid": store_id,
            "couponCode": coupon_code,
            "clCode": culture_code,
        },
        extra_headers=None,
        payload=None,
        qa_store=qa_store,
    )

    if response.status == 200:
        return json.loads(response.decoded_body)
    else:
        logger.error(
            f"[AdoraTool._apis.validate_coupon_code] Failed to validate coupon with status {response.status}: {response.decoded_body}"
        )
        return None
