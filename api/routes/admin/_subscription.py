import uuid
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import db
from api.routes.admin._auth import authorize_admin, authorize_user_account
from api.routes.admin._builder import (
    build_project_subscription,
    build_stripe_customer,
    build_subscription,
    build_subscription_plan,
)
from api.routes.admin._utils import not_found_error
from api.schemas.admin.subscription import (
    CreateCheckoutSessionRequest,
    CreateProjectSubscriptionRequest,
    CreateProjectSubscriptionResponse,
    CreateSubscriptionPlanRequest,
    CreateSubscriptionRequest,
    CreditGrant,
    GetAccountCreditResponse,
    GetCurrentSubscriptionDetailsResponse,
    GetCurrentSubscriptionResponse,
    GrantAccountCreditRequest,
    ListAccountCreditGrantsResponse,
    ListAccountSubscriptionsResponse,
    ListProjectSubscriptionsResponse,
    RemoveProjectSubscriptionResponse,
    StripeCustomer,
    Subscription,
    SubscriptionPlan,
    SwitchPlanRequest,
    SwitchPlanResponse,
    UpdateAccountSubscriptionRequest,
    UpdateAccountSubscriptionStatusRequest,
    UpdateAccountSubscriptionStatusResponse,
    UpdateStripeCustomerRequest,
    UpdateSubscriptionPlanRequest,
)
from services import account_service, project_service, subscription_service
from services.account_service import AccountParams
from services.auth_types import UserContext
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
        credit_amount=request.credit_amount,
        monthly_fee=request.monthly_fee,
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
    if hidden is not False:
        # Only admin can see hidden plans
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
    authorize_user_account(context, account_name)

    account = account_service.get_account(session, account_name)
    if not account:
        raise not_found_error(f"Account {account_name} does not exist")

    logger.info("Creating account subscription data")
    projects = retrieve_projects(session, account.id, request.project_ids)

    subscription_params = request.to_subscription_params()
    try:
        db_subscription = subscription_service.create_account_subscription(
            session,
            context,
            account,
            subscription_params,
            projects=projects,
        )
        session.commit()
    except ValueError as err:
        session.rollback()
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


def get_current_subscription(
    context: UserContext,
    session: Session,
    account_name: str,
) -> GetCurrentSubscriptionResponse:
    authorize_user_account(context, account_name)
    account = account_service.get_account(session, account_name)
    if not account:
        raise not_found_error(f"Account {account_name} does not exist")

    subscription = subscription_service.get_current_subscription(session, account)
    return GetCurrentSubscriptionResponse(
        subscription=build_subscription(subscription) if subscription else None
    )


def get_subscription_details(
    context: UserContext,
    session: Session,
    account_name: str,
):
    """
    Get comprehensive subscription and billing details.

    Returns detailed information including:
    - Current subscription and plan features
    - Usage metrics (calls used, overage)
    - Billing cycle and next billing date
    - Recent invoices with download links
    - Payment method information
    - Upgrade/downgrade options with featured benefits
    """
    authorize_user_account(context, account_name)
    account = account_service.get_account(session, account_name)
    if not account:
        raise not_found_error(f"Account {account_name} does not exist")

    details = subscription_service.get_subscription_details(session, account)

    return GetCurrentSubscriptionDetailsResponse(
        subscription=(
            build_subscription(details["subscription"])
            if details["subscription"]
            else None
        ),
        plan_name=details["plan_name"],
        plan_features=details["plan_features"],
        billing_cycle=details["billing_cycle"],
        next_billing_date=details["next_billing_date"],
        current_period_start=details["current_period_start"],
        current_period_end=details["current_period_end"],
        usage=details["usage"],
        payment_status=details["payment_status"],
        payment_method_last4=details["payment_method_last4"],
        payment_method_brand=details["payment_method_brand"],
        recent_invoices=details["recent_invoices"],
        upgrade_options=details["upgrade_options"],
        current_plan_tier=details["current_plan_tier"],
    )


def list_account_subscriptions(
    context: UserContext,
    session: Session,
    account_name: str,
) -> ListAccountSubscriptionsResponse:
    """Get all active subscriptions for an account."""
    authorize_user_account(context, account_name)

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
    authorize_user_account(context, account_name)
    if force_update:
        # Only admins can perform force updates
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
    authorize_user_account(context, account_name)

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
    authorize_user_account(context, account_name)

    try:
        cancelled_subscription = subscription_service.cancel_account_subscription(
            session, context, account_name, external_id
        )
        if cancelled_subscription is None:
            raise not_found_error("Subscription not found")
        session.commit()
        return {"message": "Subscription cancelled successfully"}
    except Exception as err:
        session.rollback()
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
    authorize_user_account(context, account_name)

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
            referral_code=request.referral_code,
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
    account_name: str,
    external_id: uuid.UUID,
) -> ListProjectSubscriptionsResponse:
    """List all project subscriptions for a given subscription external ID."""
    authorize_user_account(context, account_name)

    account = account_service.get_account(session, account_name)
    if not account:
        raise not_found_error("Account not found")

    sub = subscription_service.get_account_subscription(
        session, account.id, external_id
    )
    if not sub:
        raise not_found_error("Subscription not found")

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
    authorize_user_account(context, account_name)

    # Validate project exists
    project = project_service.get_project(session, request.project_id)
    if not project:
        raise ValueError(f"Project {request.project_id} does not exist")

    try:
        # Use external_id from path and project_id from request
        project_subscription = subscription_service.create_project_subscription(
            session, project, external_id
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
    authorize_user_account(context, account_name)

    # Validate project exists
    project = project_service.get_project(session, project_id)
    if not project:
        raise ValueError(f"Project {project_id} does not exist")

    try:
        # Use external_id and project_id from path
        subscription_service.remove_project_subscription(
            session, project.id, external_id
        )
        return RemoveProjectSubscriptionResponse(
            message="Project subscription removed successfully",
            success=True,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error removing project subscription: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


def retrieve_projects(session, account_id, project_ids) -> list[db.Project]:
    projects = []
    if project_ids:
        projects = project_service.get_projects_by_ids(session, project_ids)

    if len(projects) < len(project_ids):
        found_ids = [p.id for p in projects]
        not_found_ids = list(set(project_ids) - set(found_ids))
        raise not_found_error(f"Some project IDs not found: {not_found_ids}")
    for project in projects:
        if project.account_id != account_id:
            raise not_found_error(
                f"Project does not belong to this account: {project.id}"
            )

    return projects


def grant_credit_for_account(
    context: UserContext,
    session: Session,
    account_name: str,
    request: GrantAccountCreditRequest,
) -> StripeCustomer:
    # Only admin user can issue credit
    authorize_admin(context)

    account = account_service.get_account(session, account_name)
    if not account:
        raise not_found_error("Account not found")

    try:
        issued_by = context.email if context.role.value == "Admin" else "system"

        subscription_service.grant_credit_to_account(
            account=account,
            credit_amount_cents=request.amount,
            currency=request.currency,
            description=request.description,
            issued_by=issued_by,
            metadata={
                "issued_via": "admin_api",
                "request_source": "manual_credit_grant",
                "user_role": context.role.value,
                "actual_user": context.email,
            },
        )
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
    logger.info(
        "Successfully granted credit to account",
        extra={
            "account_name": account_name,
            "credit_amount_cents": request.amount,
            "issued_by": issued_by,
            "actual_user": context.email,
            "user_role": context.role.value,
            "description": request.description,
        },
    )
    customer = subscription_service.get_stripe_customer_info_for_account(account)
    if not customer:
        raise not_found_error(f"Stripe customer not found for account: {account_name}")

    return build_stripe_customer(customer)


def get_credit_amount(
    context: UserContext,
    session: Session,
    account_name: str,
) -> GetAccountCreditResponse:
    # Both admin and account manager can see the current credit balance
    authorize_user_account(context, account_name)

    account = account_service.get_account(session, account_name)
    if not account:
        raise ValueError("Account not found")

    balance, currency = subscription_service.get_account_credit_balance(account)

    return GetAccountCreditResponse(
        balance=balance,
        currency=currency,
    )


def list_account_credit_grants(
    context: UserContext,
    session: Session,
    account_name: str,
) -> ListAccountCreditGrantsResponse:
    authorize_admin(context)

    account = account_service.get_account(session, account_name)
    if not account:
        raise not_found_error("Account not found")

    try:
        credit_grants_data = subscription_service.get_account_credit_grants(
            account=account,
        )

        credit_grants = [
            CreditGrant(
                id=grant["id"],
                created=grant["created"],
                credit_amount_cents=grant["credit_amount_cents"],
                credit_reduction_cents=grant["credit_reduction_cents"],
                currency=grant["currency"],
                description=grant["description"],
                metadata=grant["metadata"],
                ending_balance=grant["ending_balance"],
                issued_by=grant["issued_by"],
                issued_via=grant["issued_via"],
                request_source=grant["request_source"],
            )
            for grant in credit_grants_data
        ]

        return ListAccountCreditGrantsResponse(
            credit_grants=credit_grants,
        )

    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


def switch_subscription_plan(
    context: UserContext,
    session: Session,
    account_name: str,
    request: SwitchPlanRequest,
) -> SwitchPlanResponse:
    """Switch an account's subscription plan to a new plan."""
    authorize_user_account(context, account_name)

    account = account_service.get_account(session, account_name)
    if not account:
        raise not_found_error("Account not found")

    try:
        new_subscription, old_plan_name, new_plan_name = (
            subscription_service.switch_subscription_plan(
                session=session,
                context=context,
                account=account,
                new_plan_id=request.new_plan_id,
                prorate=request.prorate,
            )
        )

        return SwitchPlanResponse(
            success=True,
            subscription_id=new_subscription.external_id,
            old_plan_name=old_plan_name,
            new_plan_name=new_plan_name,
            effective_date=new_subscription.updated_at or new_subscription.created_at,
            prorated=request.prorate,
        )

    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
    except Exception as err:
        logger.error(
            f"Failed to switch subscription plan: {err}",
            extra={
                "account_name": account_name,
                "new_plan_id": str(request.new_plan_id),
                "error": str(err),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to switch subscription plan",
        )


def unlink_subscription_from_account(
    context: UserContext,
    session: Session,
    account_name: str,
    force_unlink: bool,
):
    """Unlink a subscription from an account."""
    authorize_admin(context)

    account = account_service.get_account(session, account_name)
    if not account:
        raise not_found_error("Account not found")

    try:
        subscription_service.unlink_subscription_from_account(
            session=session,
            context=context,
            account=account,
            force_unlink=force_unlink,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        )


def create_stripe_customer(
    context: UserContext,
    session: Session,
    account_name: str,
    customer_name: str | None = None,
    customer_email: str | None = None,
) -> StripeCustomer:
    """Create a Stripe customer for an account."""
    authorize_admin(context)

    account = account_service.get_account(session, account_name)
    if not account:
        raise not_found_error("Account not found")

    try:
        customer_info = subscription_service.create_stripe_customer_for_account(
            session=session,
            context=context,
            account=account,
            customer_name=customer_name,
            customer_email=customer_email,
        )

        return build_stripe_customer(customer_info)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
    except Exception as err:
        logger.error(
            f"Failed to create Stripe customer: {err}",
            extra={
                "account_name": account_name,
                "error": str(err),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create Stripe customer",
        )


def get_stripe_customer_info(
    context: UserContext,
    session: Session,
    account_name: str,
) -> StripeCustomer:
    """Get Stripe customer information for an account."""
    authorize_user_account(context, account_name)

    account = account_service.get_account(session, account_name)
    if not account:
        raise not_found_error("Account not found")

    try:
        customer_data = subscription_service.get_stripe_customer_info_for_account(
            account=account,
        )
        if customer_data is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account has no Stripe customer",
            )
        return build_stripe_customer(customer_data)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get Stripe customer information",
        )


def update_stripe_customer_info(
    context: UserContext,
    session: Session,
    account_name: str,
    request: UpdateStripeCustomerRequest,
) -> StripeCustomer:
    """Update Stripe customer information for an account."""
    authorize_user_account(context, account_name)

    account = account_service.get_account(session, account_name)
    if not account:
        raise not_found_error("Account not found")

    try:
        customer_data = subscription_service.update_stripe_customer_for_account(
            account=account,
            name=request.name,
            email=request.email,
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update Stripe customer information",
        )
    if customer_data is None:
        raise not_found_error("Account has no Stripe customer")
    return build_stripe_customer(customer_data)
