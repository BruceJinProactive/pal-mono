import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from api.routes.admin._auth import authorize_admin
from api.routes.admin._builder import build_subscription, build_subscription_plan
from api.routes.admin._utils import UserContext
from api.schemas.admin.subscription import (
    CreateSubscriptionPlanRequest,
    CreateSubscriptionRequest,
    ListAccountSubscriptionsResponse,
    Subscription,
    UpdateAccountSubscriptionRequest,
    UpdateAccountSubscriptionStatusRequest,
    UpdateAccountSubscriptionStatusResponse,
    UpdateSubscriptionPlanRequest,
)
from services import subscription_service
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
    authorize_admin(context)
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


def list_subscription_plans(
    context: UserContext,
    session: Session,
):
    """
    Lists all subscription plans.
    """
    authorize_admin(context)
    plans = subscription_service.get_subscription_plans(session)
    return [build_subscription_plan(plan) for plan in plans]


def get_subscription_plan(
    context: UserContext,
    session: Session,
    plan_id: uuid.UUID,
):
    """
    Retrieves a subscription plan by ID.
    """
    authorize_admin(context)
    plan = subscription_service.get_subscription_plan_by_id(session, plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subscription plan {plan_id} not found",
            headers={"Content-Type": "application/json"},
        )

    return build_subscription_plan(plan)


def update_subscription_plan(
    plan_id: uuid.UUID,
    request: UpdateSubscriptionPlanRequest,
    context: UserContext,
    session: Session,
):
    """
    Updates a subscription plan by ID.
    """
    authorize_admin(context)

    plan = subscription_service.get_subscription_plan_by_id(session, plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subscription plan {plan_id} not found",
            headers={"Content-Type": "application/json"},
        )

    plan_params = request.to_subscription_plan_params()
    try:
        db_plan = subscription_service.update_subscription_plan(
            session, context, plan_id, plan_params
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
            headers={"Content-Type": "application/json"},
        )

    return build_subscription_plan(db_plan)


def expire_subscription_plan(
    plan_id: uuid.UUID,
    context: UserContext,
    session: Session,
    hard_delete: bool = False,
):
    """
    Expires or hard deletes a subscription plan by ID.
    """
    authorize_admin(context)
    try:
        expired_plan = subscription_service.expire_subscription_plan(
            session, context, plan_id, hard_delete
        )

        if hard_delete:
            return {
                "message": f"Subscription plan {plan_id} has been permanently deleted"
            }
        else:
            return build_subscription_plan(expired_plan)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
            headers={"Content-Type": "application/json"},
        )


def create_subscription(
    context: UserContext,
    session: Session,
    account_name: str,
    request: CreateSubscriptionRequest,
):
    """
    Creates a new subscription for an account.
    """
    authorize_admin(context)
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


def list_account_subscriptions(
    context: UserContext,
    session: Session,
    account_name: str,
) -> ListAccountSubscriptionsResponse:
    """Get all active subscriptions for an account."""
    authorize_admin(context)
    try:
        current, scheduled = subscription_service.get_account_subscriptions(
            session, account_name
        )

        return ListAccountSubscriptionsResponse(
            current=build_subscription(current) if current else None,
            scheduled=[build_subscription(sub) for sub in scheduled],
        )
    except ValueError as err:
        raise HTTPException(
            status_code=404,
            detail=f"Account not found: {err}",
        )
    except Exception as err:
        logger.error(f"Error retrieving account subscriptions: {err}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error",
        )


def update_subscription(
    context: UserContext,
    session: Session,
    account_name: str,
    external_id: uuid.UUID,
    request: UpdateAccountSubscriptionRequest,
    force_update: bool = False,
) -> Subscription:
    """Update an account subscription by external_id, creating a new version."""
    authorize_admin(context)

    if not request.model_dump():
        raise HTTPException(
            status_code=400,
            detail="No fields provided for update",
        )

    update_data = request.model_dump()

    try:
        new_subscription = subscription_service.update_account_subscription(
            session,
            context,
            account_name,
            external_id,
            update_data,
            force_update,
        )
        return build_subscription(new_subscription)
    except ValueError as err:
        if "does not exist" in str(err):
            raise HTTPException(
                status_code=404,
                detail=str(err),
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=str(err),
            )
    except Exception as err:
        logger.error(f"Error updating account subscription: {err}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error",
        )


def update_subscription_status(
    context: UserContext,
    session: Session,
    account_name: str,
    external_id: uuid.UUID,
    request: UpdateAccountSubscriptionStatusRequest,
) -> UpdateAccountSubscriptionStatusResponse:
    """Update the status of an account subscription."""
    authorize_admin(context)

    try:
        updated_subscription = subscription_service.update_account_subscription_status(
            session,
            context,
            account_name,
            external_id,
            request.status,
        )
        if updated_subscription is None:
            raise HTTPException(
                status_code=404,
                detail="Subscription not found",
            )
        return UpdateAccountSubscriptionStatusResponse(
            message="Subscription status updated successfully",
            external_id=updated_subscription.external_id,
            status=updated_subscription.status.value,
        )
    except ValueError as err:
        if "does not exist" in str(err):
            raise HTTPException(
                status_code=404,
                detail=str(err),
            )
        elif "Cannot update status" in str(err):
            raise HTTPException(
                status_code=400,
                detail=str(err),
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=str(err),
            )
    except Exception as err:
        logger.error(f"Error updating account subscription status: {err}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error",
        )


def cancel_subscription(
    context: UserContext,
    session: Session,
    account_name: str,
    external_id: uuid.UUID,
    hard_delete: bool = False,
) -> dict:
    """Cancel an account subscription."""
    authorize_admin(context)

    try:
        cancelled_subscription = subscription_service.cancel_account_subscription(
            session, context, account_name, external_id, hard_delete
        )

        if hard_delete:
            return {
                "message": f"Subscription {external_id} has been permanently deleted"
            }

        if cancelled_subscription is None:
            raise HTTPException(
                status_code=404,
                detail="Subscription not found",
            )
        return {"message": "Subscription cancelled successfully"}
    except ValueError as err:
        if "does not exist" in str(err):
            raise HTTPException(
                status_code=404,
                detail=str(err),
            )
        if any(
            phrase in str(err)
            for phrase in [
                "Cannot cancel",
                "Failed to cancel Stripe",
                "Cannot cancel subscription with status",
            ]
        ):
            raise HTTPException(
                status_code=400,
                detail=str(err),
            )
        raise HTTPException(
            status_code=400,
            detail=str(err),
        )
    except Exception as err:
        logger.error(f"Error cancelling account subscription: {err}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error",
        )
