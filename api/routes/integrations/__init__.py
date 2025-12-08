import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

import db
from api.routes.endpoints import endpoints
from api.routes.integrations.adora import adora_router
from api.routes.integrations.olo import olo_router
from api.routes.integrations.square import _implementation as square_implementation
from api.routes.integrations.stripe import stripe_router
from api.routes.integrations.toast import _implementation as toast_implementation
from api.routes.integrations.toast import toast_router
from api.routes.integrations.vapi import vapi_router

integrations_router = APIRouter(prefix=endpoints.INTEGRATIONS, tags=["Integrations"])

# Include the VAPI router
integrations_router.include_router(vapi_router)

# Include the Adora router
integrations_router.include_router(adora_router)

# Include the Toast router
integrations_router.include_router(toast_router)

# Include the Olo router
integrations_router.include_router(olo_router)

# Include the Stripe router
integrations_router.include_router(stripe_router)


@integrations_router.get("/square/install", status_code=status.HTTP_200_OK)
async def square_install(request: Request):
    """
    Redirects to the Square OAuth installation page for the integration.
    """
    return await square_implementation.install(request)


@integrations_router.get("/square/callback", status_code=status.HTTP_200_OK)
async def square_callback(request: Request):
    """
    Handles the callback from Square OAuth.
    """
    return await square_implementation.callback(request)


@integrations_router.post("/square/refresh-expiring", status_code=status.HTTP_200_OK)
@integrations_router.get("/square/refresh-expiring", status_code=status.HTTP_200_OK)
async def square_refresh_expiring(session=Depends(db.get_db)):
    """
    Check all Square integrations and refresh tokens that are expiring within 7 days.
    """
    try:
        result = square_implementation.check_and_refresh_expiring_square_tokens(
            session=session, days_threshold=7
        )
        return result
    finally:
        session.close()


@integrations_router.get(
    "/square/{account_name}/{integration_id}/locations", status_code=status.HTTP_200_OK
)
async def get_square_locations(account_name: str, integration_id: uuid.UUID):
    """
    Get all locations for a Square merchant.

    Args:
        account_name: Name of the account
        integration_id: UUID of the Square integration

    Returns:
        List of locations for the merchant
    """
    session = next(db.get_db())
    try:
        result = square_implementation.get_merchant_locations(
            session=session, account_name=account_name, integration_id=integration_id
        )
        return result
    finally:
        session.close()


@integrations_router.post("/square/webhook", status_code=status.HTTP_200_OK)
async def square_webhook(request: Request):
    """
    Handle Square webhook notifications for payment status updates.

    Currently handles:
    - payment.updated: Payment status changed

    Args:
        request: FastAPI request object containing the webhook payload

    Returns:
        JSONResponse: Success or error response
    """
    return await square_implementation.webhook(request)


@integrations_router.post(
    "/toast/refresh-dining-options", status_code=status.HTTP_200_OK
)
async def toast_refresh_dining_options(session=Depends(db.get_db)):
    """
    Check all Toast integrations and refresh dining options.
    """
    return toast_implementation.check_and_refresh_dining_options(session)
