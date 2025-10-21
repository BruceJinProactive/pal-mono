from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from ._implementation import (
    OloCheckoutCompleteRequest,
    checkout_complete,
    get_checkout_session,
)

olo_router = APIRouter(prefix="/olo", tags=["Integrations"])


@olo_router.get(
    "/checkout/session",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Olo checkout session payload", "model": dict},
        400: {"description": "Invalid or expired token"},
    },
)
async def checkout_session_api(t: str) -> JSONResponse:
    """
    Retrieve decrypted checkout session details for the Olo payment iframe.
    """
    return await get_checkout_session(t)


@olo_router.post(
    "/checkout/complete",
    status_code=status.HTTP_200_OK,
)
async def checkout_complete_api(
    payload: OloCheckoutCompleteRequest,
) -> JSONResponse:
    """
    Record a successful Olo checkout event from the payment iframe.
    """
    return await checkout_complete(payload)
