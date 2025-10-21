import json
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from utils.log import logger

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
    logger.debug(
        "[OloIntegration.get_checkout_session] Received token",
        extra={"token_preview": f"{token[:12]}..." if token else "missing"},
    )
    try:
        decrypted = _get_payment_iframe_fernet().decrypt(
            token.encode("utf-8"), ttl=OLO_PAYMENT_TOKEN_TTL_SECONDS
        )
    except InvalidToken as exc:
        logger.warning(
            "[OloIntegration.get_checkout_session] Invalid or expired token received",
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
            "[OloIntegration.get_checkout_session] Failed to decode token payload",
            exc_info=exc,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed token payload",
        ) from exc

    logger.debug(
        "[OloIntegration.get_checkout_session] Token decrypted",
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
        "[OloIntegration.checkout_complete] Checkout completed",
        extra={
            "basket_id": payload.basketId,
            "store_id": payload.storeId,
            "order_id": payload.orderId,
            "session_id": payload.sessionId,
        },
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "Checkout recorded"},
    )
