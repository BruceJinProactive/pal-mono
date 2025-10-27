import asyncio
import json
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from tools.olo_tool._apis import get_order_status
from tools.olo_tool.classes import OloAccessToken
from utils.log import logger
from utils.secret import get_client_secret_with_fallback

OLO_PAYMENT_TOKEN_TTL_SECONDS = 15 * 60
HARD_CODED_PAYMENT_IFRAME_SECRET = "xK8dP2m_QrZ7vN4wL9cF3bJ6hT5yU1gS0aE8iO-pMxA="


class OloCheckoutCompleteRequest(BaseModel):
    basketId: str
    storeId: str
    orderId: str
    sessionId: str | None = None
    order: dict[str, Any]
    extra: dict[str, Any] | None = None


@lru_cache(maxsize=1)
def _get_payment_iframe_fernet() -> Fernet:
    try:
        return Fernet(HARD_CODED_PAYMENT_IFRAME_SECRET.encode("utf-8"))
    except ValueError as exc:
        raise RuntimeError(
            "HARD_CODED_PAYMENT_IFRAME_SECRET must be a URL-safe base64-encoded 32-byte key"
        ) from exc


async def get_checkout_session(token: str) -> JSONResponse:
    logger.debug("[OLO] OloIntegration.get_checkout_session Received token")
    try:
        decrypted = _get_payment_iframe_fernet().decrypt(
            token.encode("utf-8"), ttl=OLO_PAYMENT_TOKEN_TTL_SECONDS
        )
    except InvalidToken as exc:
        logger.warning(
            "[OLO] OloIntegration.get_checkout_session Invalid or expired token received",
            exc_info=exc,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token",
        ) from exc

    try:
        payload = json.loads(decrypted.decode("utf-8"))
    except json.JSONDecodeError as exc:
        logger.error(
            "[OLO] OloIntegration.get_checkout_session Failed to decode token payload",
            exc_info=exc,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed token payload",
        ) from exc

    logger.debug(
        "[OLO] OloIntegration.get_checkout_session Token decrypted",
        extra={
            "store_id": payload.get("storeId"),
            "basket_id": payload.get("basketId"),
            "expires_at": payload.get("expiresAt"),
        },
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=payload,
    )


async def checkout_complete(payload: OloCheckoutCompleteRequest) -> JSONResponse:
    logger.debug(
        "[OLO] OloIntegration.checkout_complete Checkout completed",
        extra={
            "basket_id": payload.basketId,
            "store_id": payload.storeId,
            "order_id": payload.orderId,
            "session_id": payload.sessionId,
        },
    )

    api_key: str | None = None
    try:
        api_key = get_client_secret_with_fallback("OLO_MOOYAH_API_KEY").strip()
    except Exception as exc:  # pragma: no cover - secret retrieval should rarely fail
        logger.warning(
            "[OLO] OloIntegration.checkout_complete Failed to load Olo API key",
            extra={"order_id": payload.orderId},
            exc_info=exc,
        )

    if not api_key:
        logger.warning(
            "[OLO] OloIntegration.checkout_complete Skipping order status fetch; API key not configured",
            extra={"order_id": payload.orderId},
        )
    else:
        token = OloAccessToken(access_token=api_key, token_type="OloKey")
        try:
            order_status = await asyncio.to_thread(
                get_order_status,
                payload.orderId,
                token,
            )
        except Exception as exc:  # pragma: no cover - network failures are uncommon
            logger.warning(
                "[OLO] OloIntegration.checkout_complete Failed to fetch order status",
                extra={
                    "order_id": payload.orderId,
                    "store_id": payload.storeId,
                },
                exc_info=exc,
            )
        else:
            logger.debug(
                "[OLO] OloIntegration.checkout_complete Order status fetched",
                extra={
                    "order_id": payload.orderId,
                    "order_status": order_status.status.value,
                    "arrival_status": (
                        order_status.arrivalstatus.value
                        if order_status.arrivalstatus
                        else None
                    ),
                    "order_ref": order_status.orderref,
                    "total": order_status.total,
                    "payload_order_ref": payload.order.get("orderRef"),
                },
            )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "Checkout recorded"},
    )
