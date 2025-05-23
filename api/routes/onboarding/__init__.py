from fastapi import APIRouter, HTTPException, Query, status
from starlette.responses import RedirectResponse

from api.routes.endpoints import endpoints
from api.schemas.onboarding import CheckoutParams
from services import payment_service
from utils.log import logger

onboarding_router = APIRouter(prefix=endpoints.ONBOARDING, tags=["Onboarding"])


@onboarding_router.post("/checkout")
async def create_checkout_url(params: CheckoutParams):
    """
    Creates a Stripe checkout session for the account and redirect user
    to the checkout page.
    """
    session = payment_service.create_checkout_session(
        account_name=params.account_name,
        customer_email=str(params.customer_email),
        price_id=params.price_id,
        redirect_url_prefix=str(params.redirect_url_prefix),
        quantity=params.quantity,
    )
    if session and session.url:
        logger.info(
            f"Created checkout session: {session.url}", extra=params.model_dump()
        )
    else:
        logger.error("Failed to create checkout session!", extra=params.model_dump())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create checkout session!",
        )
    return RedirectResponse(url=session.url, status_code=307)
