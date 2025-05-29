from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from api.routes.admin._auth import authorize_user_account
from api.routes.admin._utils import UserContext
from api.schemas.admin.subscription import CheckoutParams
from services import account_service, payment_service
from services.account_service import AccountParams
from utils.log import logger


def create_checkout_url(params: CheckoutParams, context: UserContext):
    """
    Creates a Stripe checkout session for the account and redirect user
    to the checkout page.

    Args:
        params: Checkout parameters including account name, email, etc.
        context: User context for authentication
    """
    # Authorize user access to the account
    authorize_user_account(context, params.account_name)

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


def update_account_subscription(
    db_session: Session,
    checkout_session_id: str,
    context: UserContext,
):
    """
    Extracts metadata from stripe's checkout session and updates the account's subscription data.

    Args:
        db_session: Database session
        checkout_session_id: Stripe checkout session ID
        context: User context for authentication
    """
    checkout_data = payment_service.unpack_checkout_session(checkout_session_id)
    if not checkout_data:
        raise ValueError("Failed to retrieve checkout session.")

    account_name = checkout_data["account_name"]
    customer_id = checkout_data["customer_id"]
    subscription_id = checkout_data["subscription_id"]

    # Authorize user access to the account
    authorize_user_account(context, account_name)

    # Use the authenticated user context instead of creating a guest context
    account_service.update_account(
        db_session,
        context,
        account_name,
        AccountParams(
            stripe_customer_id=customer_id,
            stripe_subscription_id=subscription_id,
        ),
    )
