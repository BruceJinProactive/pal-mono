import uuid
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from api.routes.admin._auth import authorize_admin, authorize_user_account
from api.routes.admin._builder import (
    build_project_subscription,
    build_subscription,
    build_subscription_plan,
)
from api.routes.admin._utils import UserContext, not_found_error
from api.schemas.admin.subscription import (
    CreateCheckoutSessionRequest,
    CreateProjectSubscriptionRequest,
    CreateProjectSubscriptionResponse,
    CreateSubscriptionPlanRequest,
    CreateSubscriptionRequest,
    ListAccountSubscriptionsResponse,
    ListProjectSubscriptionsResponse,
    RemoveProjectSubscriptionResponse,
    Subscription,
    SubscriptionPlan,
    UpdateAccountSubscriptionRequest,
    UpdateAccountSubscriptionStatusRequest,
    UpdateAccountSubscriptionStatusResponse,
    UpdateSubscriptionPlanRequest,
)
from services import (
    account_service,
    project_service,
    subscription_service,
)
from services.account_service import AccountParams
from services.subscription_service.schema import SubscriptionPlanParams
from utils.log import logger


def create_subscription_plan(
    context: UserContext,
    session: Session,
    request: CreateSubscriptionPlanRequest,
) -> SubscriptionPlan:
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
        hidden=request.hidden,
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
    hidden: Optional[bool] = None,
):
    """
    Lists all subscription plans, optionally filtered by hidden status.

    Args:
        context: User context for authorization
        session: Database session
        hidden: Optional filter for hidden status (None = all, True = hidden only, False = not hidden only)
    """
    authorize_admin(context)
    plans = subscription_service.get_subscription_plans(session, hidden=hidden)
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
    context: UserContext,
    session: Session,
    plan_id: uuid.UUID,
    request: UpdateSubscriptionPlanRequest,
) -> SubscriptionPlan:
    authorize_admin(context)

    try:
        updated_plan = subscription_service.update_subscription_plan(
            session, context, plan_id, request.to_subscription_plan_params()
        )
        return build_subscription_plan(updated_plan)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
            headers={"Content-Type": "application/json"},
        )


def delete_subscription_plan(
    plan_id: uuid.UUID,
    hard_delete: bool,
    context: UserContext,
    session: Session,
):
    authorize_admin(context)
    try:
        subscription_service.delete_subscription_plan(
            session, context, plan_id, hard_delete
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
            headers={"Content-Type": "application/json"},
        )


def create_account_subscription(
    context: UserContext,
    session: Session,
    account_name: str,
    request: CreateSubscriptionRequest,
):
    """
    Creates a new subscription for an account.
    """
    authorize_admin(context)

    account = account_service.get_account(session, account_name)
    if not account:
        raise not_found_error(f"Account {account_name} does not exist")

    subscription_params = request.to_subscription_params()
    try:
        db_subscription = subscription_service.create_account_subscription(
            session,
            context,
            account.id,
            subscription_params,
            project_ids=request.project_ids or [],
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

    account = account_service.get_account(session, account_name)
    if not account:
        raise not_found_error(f"Account {account_name} does not exist")

    try:
        current, scheduled = subscription_service.get_account_subscriptions(
            session, account.id
        )

        return ListAccountSubscriptionsResponse(
            current=build_subscription(current) if current else None,
            scheduled=[build_subscription(sub) for sub in scheduled],
        )
    except ValueError as err:
        raise not_found_error(f"Account not found: {err}")
    except Exception as err:
        logger.error(f"Error retrieving account subscriptions: {err}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error",
        )


def update_account_subscription(
    context: UserContext,
    session: Session,
    account_name: str,
    external_id: uuid.UUID,
    request: UpdateAccountSubscriptionRequest,
    force_update: bool = False,
) -> Subscription:
    """Update an account subscription by external_id, creating a new version."""
    authorize_admin(context)

    account = account_service.get_account(session, account_name)
    if not account:
        raise not_found_error(f"Account {account_name} not found!")

    update_data = request.model_dump()
    if not update_data:
        raise HTTPException(
            status_code=400,
            detail="No fields provided for update",
        )

    try:
        new_subscription = subscription_service.update_account_subscription(
            session,
            context,
            account.id,
            external_id,
            update_data,
            force_update,
        )
        return build_subscription(new_subscription)
    except ValueError as err:
        raise HTTPException(
            status_code=404,
            detail=str(err),
        )
    except Exception as err:
        logger.error(f"Error updating account subscription: {err}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error",
        )


def update_account_subscription_status(
    context: UserContext,
    session: Session,
    account_name: str,
    external_id: uuid.UUID,
    request: UpdateAccountSubscriptionStatusRequest,
) -> UpdateAccountSubscriptionStatusResponse:
    """Update the status of an account subscription."""
    authorize_admin(context)

    account = account_service.get_account(session, account_name)
    if not account:
        raise not_found_error(f"Account {account_name} not found.")

    try:
        updated_subscription = subscription_service.update_account_subscription_status(
            session,
            context,
            account.id,
            external_id,
            request.status,
        )
        if updated_subscription is None:
            raise not_found_error("Subscription not found")

        return UpdateAccountSubscriptionStatusResponse(
            message="Subscription status updated successfully",
            external_id=updated_subscription.external_id,
            status=updated_subscription.status.value,
        )
    except ValueError as err:
        if "does not exist" in str(err):
            raise not_found_error(str(err))
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


def cancel_account_subscription(
    context: UserContext,
    session: Session,
    account_name: str,
    external_id: uuid.UUID,
) -> dict:
    """Cancel an account subscription."""
    authorize_admin(context)

    try:
        cancelled_subscription = subscription_service.cancel_account_subscription(
            session, context, account_name, external_id
        )

        if cancelled_subscription is None:
            raise not_found_error("Subscription not found")
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


def create_checkout_session(
    context: UserContext,
    session: Session,
    account_name: str,
    external_id: uuid.UUID,
    request: CreateCheckoutSessionRequest,
) -> str:
    """Create a Stripe checkout session for a subscription."""
    authorize_admin(context)

    # Get account to validate it exists
    account = account_service.get_account(session, account_name)
    if not account:
        raise not_found_error(f"Account {account_name} not found")

    try:
        checkout_url = subscription_service.create_stripe_checkout_url(
            session=session,
            account_id=account.id,
            external_id=external_id,
            customer_email=(
                str(request.customer_email) if request.customer_email else None
            ),
            redirect_url_prefix=str(request.redirect_url_prefix),
        )
    except RuntimeError as err:
        logger.exception(str(err))
        raise HTTPException(
            status_code=500,
            detail=str(err),
        )
    except ValueError as err:
        raise HTTPException(
            status_code=400,
            detail=str(err),
        )

    if not checkout_url:
        raise not_found_error(
            f"Subscription {external_id} not found in account: {account_name}"
        )

    return checkout_url


def handle_subscription_checkout_callback(
    context: UserContext,
    session: Session,
    session_id: str,
):
    checkout_response = subscription_service.handle_stripe_checkout_success(
        session, context, session_id
    )
    if not checkout_response:
        raise not_found_error("Invalid session id or checkout not successful")

    account = account_service.get_account_by_id(session, checkout_response.account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The account linked in the checkout session does not exist",
        )

    authorize_user_account(context, account.name)

    account_service.update_account(
        session,
        context,
        account.name,
        AccountParams(
            stripe_customer_id=checkout_response.customer_id,
        ),
    )


def list_project_subscriptions_by_subscription_external_id(
    context: UserContext,
    session: Session,
    external_id: uuid.UUID,
) -> ListProjectSubscriptionsResponse:
    """List all project subscriptions for a given subscription external ID."""
    authorize_admin(context)

    try:
        project_subscriptions = (
            subscription_service.get_project_subscriptions_by_subscription_external_id(
                session, context, external_id
            )
        )

        # Collect project IDs and fetch projects
        project_ids = [ps.project_id for ps in project_subscriptions]
        projects = project_service.get_projects_by_ids(session, project_ids)

        # Create a mapping for quick lookup
        projects_by_id = {project.id: project for project in projects}

        # Build response objects
        project_subscription_responses = []
        for ps in project_subscriptions:
            project = projects_by_id.get(ps.project_id)
            if project:
                project_subscription_responses.append(
                    build_project_subscription(ps, project)
                )

        return ListProjectSubscriptionsResponse(
            project_subscriptions=project_subscription_responses,
            total_count=len(project_subscription_responses),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error listing project subscriptions: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


def create_project_subscription(
    context: UserContext,
    session: Session,
    account_name: str,
    external_id: uuid.UUID,
    request: CreateProjectSubscriptionRequest,
) -> CreateProjectSubscriptionResponse:
    """Create a new project subscription."""
    authorize_admin(context)

    try:
        # Use external_id from path and project_id from request
        project_subscription, project = (
            subscription_service.create_project_subscription(
                session, context, request.project_id, external_id
            )
        )

        # Build response object
        project_subscription_response = build_project_subscription(
            project_subscription, project
        )

        return CreateProjectSubscriptionResponse(
            message="Project subscription created successfully",
            project_subscription=project_subscription_response,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating project subscription: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


def remove_project_subscription(
    context: UserContext,
    session: Session,
    account_name: str,
    external_id: uuid.UUID,
    project_id: uuid.UUID,
) -> RemoveProjectSubscriptionResponse:
    """Remove a project subscription."""
    authorize_admin(context)

    try:
        # Use external_id and project_id from path
        success = subscription_service.remove_project_subscription(
            session, context, project_id, external_id
        )

        if success:
            return RemoveProjectSubscriptionResponse(
                message="Project subscription removed successfully",
                success=True,
            )
        else:
            return RemoveProjectSubscriptionResponse(
                message="Failed to remove project subscription",
                success=False,
            )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error removing project subscription: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
