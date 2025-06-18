from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from api.routes.admin._auth import authorize_user_account
from api.routes.admin._builder import build_subscription, build_subscription_plan
from api.routes.admin._utils import UserContext
from api.schemas.admin.subscription import (
    CheckoutParams,
    CreateSubscriptionPlanRequest,
    CreateSubscriptionRequest,
)
from services import account_service, payment_service, subscription_service
from services.account_service import AccountParams
from services.subscription_service.schema import SubscriptionPlanParams
from utils.log import logger


def create_subscription_plan(
    context: UserContext,
    session: Session,
    request: CreateSubscriptionPlanRequest,
):
    """
    Creates a new subscription plan.
    """
    plan_params = SubscriptionPlanParams(
        name=request.name,
        description=request.description,
        tier=request.tier,
        features_included=request.features_included,
        features_excluded=request.features_excluded,
        call_quota=request.call_quota,
        order_quota=request.order_quota,
        call_overage_charge=request.call_overage_charge,
        order_overage_charge=request.order_overage_charge,
        free_trial_days=request.free_trial_days,
        monthly_fee=request.monthly_fee,
        stripe_price_id=request.stripe_price_id,
        active=request.active,
        sort_id=request.sort_id,
    )

    try:
        db_plan = subscription_service.create_subscription_plan(
            session,
            context,
            plan_params,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
            headers={"Content-Type": "application/json"},
        )

    if db_plan is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create subscription plan",
        )

    return build_subscription_plan(db_plan)


def create_subscription(
    context: UserContext,
    session: Session,
    account_name: str,
    request: CreateSubscriptionRequest,
):
    """
    Creates a new subscription for an account.
    """
    # Authorize user access to the account
    authorize_user_account(context, account_name)
    subscription_params = request.to_subscription_params()
    try:
        db_subscription = subscription_service.create_subscription(
            session,
            context,
            account_name,
            subscription_params,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
            headers={"Content-Type": "application/json"},
        )
    if db_subscription is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create subscription",
        )
    return build_subscription(db_subscription)


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
    return session.url


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
