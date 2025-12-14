import threading

from utils.log import logger

from ._utils import connect_adora_order_hub, connect_adora_token_hub


async def get_adora_pos_auth_token(key: str, secret: str) -> str | None:
    """Retrieve an Adora POS authentication token."""
    logger.debug(
        f"[AdoraV2Tool._apis.get_adora_pos_auth_token] Thread: {threading.current_thread().name} (ID: {threading.current_thread().ident})"
    )

    if not key or not secret:
        logger.error(f"[AdoraV2Tool._apis] Missing {'key' if not key else 'secret'}")
        return None

    try:
        response = await connect_adora_token_hub(key, secret)

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
        f"[AdoraV2Tool._apis.check_store_status] Thread: {threading.current_thread().name} (ID: {threading.current_thread().ident})"
    )

    try:
        response = await connect_adora_order_hub(
            "GET",
            bearer_token,
            "store/status",
            query_params={"sid": store_id},
        )

        if response["status"] == 200:
            return response["body"]

        logger.error(f"[AdoraV2Tool._apis] Error {response}")
        return None
    except Exception as e:
        logger.error(f"[AdoraV2Tool._apis] Request error: {e}")
        return None


async def api_get_store_info(
    bearer_token: str, store_id: str, date: str
) -> dict | None:
    """Get store information for a specific date."""
    logger.debug(
        f"[AdoraV2Tool._apis.api_get_store_info] Thread: {threading.current_thread().name} (ID: {threading.current_thread().ident})"
    )

    try:
        response = await connect_adora_order_hub(
            "GET",
            bearer_token,
            "store/info",
            query_params={"sid": store_id, "date": date},
        )

        if response["status"] == 200:
            return response["body"]

        logger.error(f"[AdoraV2Tool._apis] Error {response}")
        return None
    except Exception as e:
        logger.error(f"[AdoraV2Tool._apis] Request error: {e}")
        return None
