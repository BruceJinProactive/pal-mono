import os
import threading
from enum import Enum

import httpx

from utils.log import logger

TIMEOUT_SECONDS = 10


MARCOS_STORE_IDS = {
    s.strip() for s in os.getenv("MARCOS_STORE_IDS", "").split(",") if s.strip()
}


class ApiFunction(Enum):
    STORE_INFO = "store/info"
    STORE_STATUS = "store/status"
    VALIDATE_ADDRESS = "validateAddress"
    VALIDATE_COUPON = "validateCouponCode"
    VALIDATE_ORDER = "validateOrder"
    PROCESS_ORDER = "processOrder"


class HttpMethod(Enum):
    GET = "GET"
    POST = "POST"


V1_API_FUNCTIONS = {
    ApiFunction.STORE_INFO,
    ApiFunction.STORE_STATUS,
    ApiFunction.VALIDATE_ADDRESS,
    ApiFunction.VALIDATE_COUPON,
}

V2_API_FUNCTIONS = {
    ApiFunction.VALIDATE_ORDER,
    ApiFunction.PROCESS_ORDER,
}


async def connect_adora_token_hub(
    key: str,
    secret: str,
    store_id: str,
) -> dict:
    """Utility function to connect to Adora Token Hub API."""
    logger.debug(
        f"[AdoraV2Tool._apis._utils] connect to adora token hub on thread: {threading.current_thread().name} (ID: {threading.current_thread().ident})"
    )

    url = get_endpoint_url(store_id=store_id, request_token=True)

    try:
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        data = {
            "grant_type": "client_credentials",
            "client_id": key,
            "client_secret": secret,
        }

        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.post(
                url=url,
                data=data,
                headers=headers,
            )

            return {
                "status": response.status_code,
                "reason": response.reason_phrase,
                "body": response.json() if response.text else {},
            }
    except Exception as e:
        logger.error(f"[AdoraV2Tool._apis._utils] Token request failed: {e}")
        return {"status": 500, "reason": str(e), "body": {}}


async def connect_adora_order_hub(
    http_method: HttpMethod,
    bearer_token: str,
    api_function: ApiFunction,
    query_params: dict | None = None,
    extra_headers: dict | None = None,
    payload: dict | None = None,
) -> dict:
    """Utility function to connect to Adora Order Hub API."""
    logger.debug(
        f"[AdoraV2Tool._apis._utils] connect to adora order hub with function: {api_function} on thread: {threading.current_thread().name} (ID: {threading.current_thread().ident}), method: {http_method}, function: {api_function}"
    )

    store_id = get_store_id(query_params, payload)

    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": bearer_token,
        }
        if extra_headers:
            headers.update(extra_headers)

        url = get_endpoint_url(store_id, api_function, request_token=False)
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.request(
                method=http_method.value,
                url=url,
                params=query_params,
                json=payload,
                headers=headers,
            )

            return {
                "status": response.status_code,
                "reason": response.reason_phrase,
                "body": response.json() if response.text else {},
            }
    except Exception as e:
        logger.error(
            f"[AdoraV2Tool._apis._utils] Request to adora order hub failed: {e}"
        )
        return {"status": 500, "reason": str(e), "body": {}}


def get_store_id(query_params: dict | None, payload: dict | None) -> str:
    if query_params and "sid" in query_params:
        return query_params["sid"]

    # Check for both camelCase (storeId) and snake_case (store_id) in payload
    if payload:
        if "storeId" in payload:
            return payload["storeId"]
        if "store_id" in payload:
            return payload["store_id"]

    error_msg = "store_id not found in query_params or payload"
    logger.error(f"[AdoraV2Tool._apis._utils] {error_msg}")
    raise ValueError(error_msg)


def get_endpoint_url(
    store_id: str, api_function: ApiFunction | None = None, *, request_token: bool
) -> str:
    if request_token:
        if store_id in ("UQ5ZT", "LE5AR"):
            return "https://identityqa.adorapos.com/connect/token"
        elif store_id in MARCOS_STORE_IDS:
            return "https://identity.marcosoms.com/connect/token"
        else:
            return "https://identity.adorapos.net/connect/token"
    else:
        if api_function is None:
            raise ValueError("api_function is required when request_token=False")
        if store_id in ("UQ5ZT", "LE5AR"):
            base_url = "https://adora-qa-api-public.azurewebsites.net"
        elif store_id in MARCOS_STORE_IDS:
            base_url = "https://papi.marcosoms.com"
        else:
            base_url = "https://public.api.adorapos.net"

        # Determine API version based on function
        if api_function in V1_API_FUNCTIONS:
            api_version = "v1"
        elif api_function in V2_API_FUNCTIONS:
            api_version = "v2"
        else:
            raise ValueError(f"Unknown API function: {api_function}")

        return f"{base_url}/api/{api_version}/OrderHub/{api_function.value}"
