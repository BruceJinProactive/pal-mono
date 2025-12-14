import threading

import httpx

from utils.log import logger

TIMEOUT_SECONDS = 10


async def connect_adora_token_hub(
    key: str,
    secret: str,
) -> dict:
    """Utility function to connect to Adora Token Hub API."""
    logger.debug(
        f"[AdoraV2Tool._apis.connect_adora_token_hub] Thread: {threading.current_thread().name} (ID: {threading.current_thread().ident})"
    )

    endpoint = "https://identity.adorapos.net/connect/token"

    try:
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        data = {
            "grant_type": "client_credentials",
            "client_id": key,
            "client_secret": secret,
        }

        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.post(
                url=endpoint,
                data=data,
                headers=headers,
            )

            return {
                "status": response.status_code,
                "reason": response.reason_phrase,
                "body": response.json() if response.text else {},
            }
    except Exception as e:
        logger.error(f"[AdoraV2Tool._apis] Token request failed: {e}")
        return {"status": 500, "reason": str(e), "body": {}}


async def connect_adora_order_hub(
    http_method: str,
    bearer_token: str,
    api_function: str,
    query_params: dict | None = None,
    extra_headers: dict | None = None,
    payload: dict | None = None,
    version: str = "v1",
) -> dict:
    """Utility function to connect to Adora Order Hub API."""
    logger.debug(
        f"[AdoraV2Tool._apis.connect_adora_order_hub] Thread: {threading.current_thread().name} (ID: {threading.current_thread().ident}), method: {http_method}, function: {api_function}"
    )

    endpoint = "https://public.api.adorapos.net"

    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": bearer_token,
        }
        if extra_headers:
            headers.update(extra_headers)

        url = f"{endpoint}/api/{version}/OrderHub/{api_function}"

        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.request(
                method=http_method,
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
        logger.error(f"[AdoraV2Tool._apis] Request failed: {e}")
        return {"status": 500, "reason": str(e), "body": {}}
