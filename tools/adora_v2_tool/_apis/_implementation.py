import json
import threading
from typing import Tuple

import aioboto3
import httpx
from botocore.exceptions import BotoCoreError, ClientError

from tools.adora_v2_tool.classes import (
    DeliveryAddress,
    ValidateOrderRequest,
    ValidateOrderResponse,
)
from utils.log import logger
from utils.secret import AWS_REGION, async_get_server_secret_with_fallback

from ._utils import (
    ApiFunction,
    HttpMethod,
    connect_adora_order_hub,
    connect_adora_token_hub,
)


async def get_adora_pos_auth_token(key: str, secret: str, store_id: str) -> str | None:
    """Retrieve an Adora POS authentication token."""
    logger.debug(
        f"[AdoraV2Tool._apis] Thread: {threading.current_thread().name} (ID: {threading.current_thread().ident})"
    )

    if not key or not secret:
        logger.error(f"[AdoraV2Tool._apis] Missing {'key' if not key else 'secret'}")
        return None

    try:
        response = await connect_adora_token_hub(key, secret, store_id)

        if response["status"] != 200:
            logger.error(
                f"[AdoraV2Tool._apis] Token request failed: {response['status']}"
            )
            return None

        token_data = response["body"]
        if access_token := token_data.get("access_token"):
            return f"{token_data.get('token_type', 'Bearer')} {access_token}"

        logger.error("[AdoraV2Tool._apis] No access_token in response")
        return None

    except Exception as e:
        logger.error(f"[AdoraV2Tool._apis] Error: {e}")
        return None


async def api_check_store_ordering_status(
    bearer_token: str, store_id: str
) -> dict | None:
    """Check the online ordering status of the store."""
    logger.debug(
        f"[AdoraV2Tool._apis] Get store ordering status on thread: {threading.current_thread().name} (ID: {threading.current_thread().ident})"
    )

    try:
        response = await connect_adora_order_hub(
            HttpMethod.GET,
            bearer_token,
            ApiFunction.STORE_STATUS,
            query_params={"sid": store_id},
        )

        if response["status"] == 200:
            return response["body"]

        logger.error(f"[AdoraV2Tool._apis] Error {response}")
        return None
    except (KeyError, TypeError, httpx.RequestError) as e:
        logger.error(f"[AdoraV2Tool._apis] Request error: {e}")
        return None


async def api_get_store_info(
    bearer_token: str, store_id: str, date: str
) -> dict | None:
    """Get store information for a specific date."""
    logger.debug(
        f"[AdoraV2Tool._apis] get store info on thread: {threading.current_thread().name} (ID: {threading.current_thread().ident})"
    )

    try:
        response = await connect_adora_order_hub(
            HttpMethod.GET,
            bearer_token,
            ApiFunction.STORE_INFO,
            query_params={"sid": store_id, "date": date},
        )

        if response["status"] == 200:
            return response["body"]

        logger.error(f"[AdoraV2Tool._apis] Error {response}")
        return None
    except (KeyError, TypeError, httpx.RequestError) as e:
        logger.error(f"[AdoraV2Tool._apis] Request error: {e}")
        return None


async def api_validate_address(
    bearer_token: str,
    store_id: str,
    delivery_address: DeliveryAddress,
    street_no: str,
    street_name: str,
) -> list[dict] | dict | str:
    """
    Validate an address with Adora POS.

    Returns:
        Address validation result (list/dict) on success, error message string on failure
    """
    try:
        payload = {
            "store_id": store_id,
            "lat": delivery_address.lat,
            "lng": delivery_address.lng,
            "streetNo": street_no,
            "streetName": street_name,
            "unitApt": delivery_address.extended_address,
            "city": delivery_address.city,
            "state": delivery_address.state,
            "zip": delivery_address.zip,
        }

        response = await connect_adora_order_hub(
            HttpMethod.POST, bearer_token, ApiFunction.VALIDATE_ADDRESS, payload=payload
        )

        body = response.get("body", {})

        if response["status"] == 200:
            if isinstance(body, (list, dict)):
                return body
            if isinstance(body, str):
                return json.loads(body)

        return (
            body.get("message", "Address validation failed")
            if isinstance(body, dict)
            else str(body)
        )

    except Exception as e:
        logger.error(f"[api_validate_address] Error: {e}")
        return "An error occurred while validating the address."


async def geocode_with_google(
    delivery_address: DeliveryAddress,
) -> Tuple[float, float] | None:
    """Async Google Geocoding API call using httpx."""
    try:
        GOOGLE_GEOCODING_URL = "https://maps.googleapis.com/maps/api/geocode/json"
        # Build address string
        address_parts = [
            p
            for p in [
                delivery_address.address,
                delivery_address.city,
                delivery_address.state,
                delivery_address.zip,
            ]
            if p and p != "N/A"
        ] + ["USA"]

        address_string = ", ".join(address_parts)

        # Get API key asynchronously
        api_key = await async_get_server_secret_with_fallback("GOOGLE_GEOCODE_API_KEY")

        # Make async request
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                GOOGLE_GEOCODING_URL,
                params={
                    "address": address_string,
                    "key": api_key,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            # Parse response
            if data.get("status") == "OK" and data.get("results"):
                location = data["results"][0]["geometry"]["location"]
                return location["lat"], location["lng"]

            logger.warning(f"[geocode_with_google] No results: {data.get('status')}")
            return None

    except (httpx.TimeoutException, httpx.HTTPStatusError, Exception) as e:
        logger.error(f"[geocode_with_google] Error: {e}")
        return None


async def geocode_with_aws_location(
    delivery_address: DeliveryAddress,
) -> Tuple[float, float] | None:
    """Async AWS geo-places service call using aioboto3."""
    try:
        # Build address string
        address_parts = [
            p
            for p in [
                delivery_address.address,
                delivery_address.city,
                delivery_address.state,
                delivery_address.zip,
            ]
            if p and p != "N/A"
        ] + ["USA"]

        address_string = ", ".join(address_parts)

        # Make async AWS request
        session = aioboto3.Session()
        async with session.client(
            "geo-places", region_name=AWS_REGION
        ) as client:  # type: ignore[reportGeneralTypeIssues]
            response = await client.geocode(
                QueryText=address_string,
                MaxResults=1,
                QueryComponents={"Country": "USA"},
            )

            if response.get("ResultItems"):
                longitude, latitude = response["ResultItems"][0]["Position"]
                return latitude, longitude

            logger.warning("[geocode_with_aws_location] No results found")
            return None

    except (ClientError, BotoCoreError) as e:
        logger.error(f"[geocode_with_aws_location] Error: {e}")
        return None


async def api_validate_order(
    bearer_token: str, order_request: ValidateOrderRequest
) -> ValidateOrderResponse | str:
    """
    Validate a customer order with Adora POS.

    Args:
        bearer_token: Bearer token for authentication
        order_request: ValidateOrderRequest containing all order details

    Returns:
        ValidateOrderResponse on success, error message string on failure
    """
    try:
        payload = order_request.model_dump(by_alias=True, exclude_none=True)

        response = await connect_adora_order_hub(
            HttpMethod.POST,
            bearer_token,
            ApiFunction.VALIDATE_ORDER,
            payload=payload,
        )

        body = response.get("body", {})

        if response["status"] == 200:
            validated_response = ValidateOrderResponse(**body)
            return f"Success:\n{validated_response}"

        return (
            body.get("message", "Order validation failed")
            if isinstance(body, dict)
            else str(body)
        )

    except Exception as e:
        logger.error(f"[api_validate_order] Error: {e}")
        return "An error occurred while validating the order."
