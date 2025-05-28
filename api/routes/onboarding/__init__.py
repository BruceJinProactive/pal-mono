from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

import db
from api.routes.endpoints import endpoints
from api.schemas.onboarding import CheckoutParams
from services import admin_service

from . import _subscription

onboarding_router = APIRouter(prefix=endpoints.ONBOARDING, tags=["Onboarding"])


@onboarding_router.post("/checkout")
async def create_checkout_url(params: CheckoutParams):
    """
    Creates a Stripe checkout session for the account and redirect user
    to the checkout page.
    """
    return _subscription.create_checkout_url(params)


@onboarding_router.post("/update_subscription", status_code=200)
async def update_subscription_data(
    checkout_session_id: str = Query(..., description="Checkout Session ID"),
    db_session: Session = Depends(db.get_db),
):
    """
    Extracts metadata from stripe's checkout session and updates the account's subscription data.
    """
    return _subscription.update_account_subscription(db_session, checkout_session_id)
