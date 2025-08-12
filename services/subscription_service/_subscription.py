import copy
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, List, Optional

from sqlalchemy.orm import Session

import db
from api.routes.admin import UserContext
from db.db_utils import duplicate_row
from db.repositories.subscription_repository import (
    AccountSubscriptionRepository,
    ProjectSubscriptionRepository,
    SubscriptionPlanRepository,
)
from db.tables.change_log import ChangeResourceType
from db.tables.subscriptions import SubscriptionStatus
from services import account_service, project_service
from services.history_service import change_log_context
from services.subscription_service import _stripe
from services.subscription_service.schema import (
    StripeCheckoutResponse,
    SubscriptionParams,
)
from utils.log import logger


def handle_stripe_checkout_success(
    session: Session,
    context: UserContext,
    session_id: str,
) -> StripeCheckoutResponse | None:
    response = _stripe.handle_checkout_success(session_id)
    if not response:
        return response

    data = {
        "stripe_subscription_id": response.stripe_subscription_id,
    }
    update_account_subscription(
        session, context, response.account_id, response.subscription_external_id, data
    )
    logger.info(
        "Successfully updated subscription's stripe id",
        extra={
            "account_subscription_id": response.subscription_external_id,
            "stripe_subscription_id": response.stripe_subscription_id,
        },
    )
    return response


def get_subscription_plan_by_id(
    session: Session,
    plan_id: uuid.UUID,
) -> Optional[db.SubscriptionPlan]:
    """
    Get a subscription plan by ID.

    Args:
        session: Database session
        plan_id: Plan ID to retrieve

    Returns:
        Subscription plan if found, None otherwise
    """
    subscription_plan_repository = SubscriptionPlanRepository(
        session, auto_commit=False
    )
    return subscription_plan_repository.get_subscription_plan_by_id(plan_id)


def _validate_subscription_request(params: SubscriptionParams, plan):
    """Validate subscription request parameters."""
    if not params.subscription_plan_id:
        raise ValueError("Missing subscription_plan_id in request")

    if not plan.active:
        raise ValueError("Cannot create subscription for inactive plan")


def _validate_contract_overrides(override):
    """Validate that contract subscriptions have all required override fields."""
    if not override:
        raise ValueError("Contract subscriptions require override parameters")

    required_fields = [
        "start_date",
        "end_date",
        "call_quota",
        "order_quota",
        "call_overage_charge",
        "order_overage_charge",
        "monthly_fee",
    ]

    missing_fields = [
        field for field in required_fields if getattr(override, field) is None
    ]

    if missing_fields:
        raise ValueError(
            f"Contract subscriptions require all override fields. Missing: {', '.join(missing_fields)}"
        )


def _extract_subscription_parameters(params: SubscriptionParams, plan):
    """Extract subscription parameters from override or plan defaults."""
    now = datetime.now(UTC)
    default_start = now + timedelta(days=plan.free_trial_days or 0)
    default_end = default_start.replace(year=default_start.year + 7)
    return {
        "trial_start_date": _get_param_value(params.schedule, "trial_start_date", now),
        "start_date": _get_param_value(params.schedule, "start_date", default_start),
        "end_date": _get_param_value(params.schedule, "end_date", default_end),
    }


def create_account_subscription(
    session: Session,
    context: UserContext,
    account_id: uuid.UUID,
    params: SubscriptionParams,
    project_ids: List[uuid.UUID],
) -> db.AccountSubscription:
    """
    Create a new account subscription according to the specification.

    Business Logic:
    - If any field is present in the override, use that, otherwise calculate according to logic
    - If subscription type is contract, everything must be listed in the override section
    - Cannot create new subscription if start_date and end_date overlaps with existing active subscription of same type
    - New subscription always has 'active' status
    - If project_ids are provided, create ProjectSubscription entries for each project

    Date Logic:
    - Trial start_date: now
    - Monthly start_date: end_date of last free trial (if exists), otherwise now
    - Trial end_date: start_date + free_trial_days from plan
    - Monthly end_date: start_date + 7 years (arbitrary and subject to change)
    """
    if project_ids:
        _validate_project_ids(session, account_id, project_ids)

    subscription_plan_repository = SubscriptionPlanRepository(session)
    account_subscription_repository = AccountSubscriptionRepository(
        session, auto_commit=False
    )
    project_subscription_repository = ProjectSubscriptionRepository(
        session, auto_commit=False
    )

    plan = subscription_plan_repository.get_subscription_plan_by_id(
        params.subscription_plan_id
    )
    if not plan:
        raise ValueError(f"Subscription plan '{params.subscription_plan_id}' not found")

    _validate_subscription_request(params, plan)

    subscription_params = _extract_subscription_parameters(params, plan)
    account_subscription = db.AccountSubscription(
        external_id=uuid.uuid4(),
        account_id=account_id,
        subscription_plan_id=plan.id,
        status=SubscriptionStatus.pending,
        payment_method=params.payment_method,
        **subscription_params,
    )

    if account_subscription_repository.check_subscription_overlap(
        account_id,
        account_subscription.start_date,
        account_subscription.end_date,
    ):
        raise ValueError(
            "Cannot create subscription: overlaps with existing active subscriptions"
        )

    with change_log_context(
        session=session,
        resource_type=ChangeResourceType.Subscription,
        author=context.email,
        account_id=account_id,
        auto_commit=False,
    ) as ctx:
        subscription = account_subscription_repository.create_account_subscription(
            account_subscription
        )
        ctx.resource_id = str(subscription.external_id)
        ctx.new_record = subscription

    logger.info(
        f"Created subscription for account {account_id}",
        extra={
            "account_id": str(account_id),
            "subscription_id": str(subscription.id),
            "plan_id": str(plan.id),
            "project_ids": [str(pid) for pid in project_ids or []],
            "trial_start_date": (
                subscription.trial_start_date.isoformat()
                if subscription.trial_start_date
                else None
            ),
            "start_date": subscription.start_date.isoformat(),
            "end_date": subscription.end_date.isoformat(),
        },
    )

    # Create ProjectSubscription entries if project_ids are provided
    for project_id in project_ids or []:
        project_subscription_repository.create_project_subscription(
            project_id,
            subscription.external_id,
        )

    session.commit()
    return subscription


def _validate_project_ids(
    session: Session, account_id: uuid.UUID, project_ids: list[uuid.UUID]
):
    # Validate that all project_ids belong to the account
    account_projects = project_service.get_projects_by_account_id(session, account_id)
    account_project_ids = {p.id for p in account_projects}

    invalid_project_ids = [pid for pid in project_ids if pid not in account_project_ids]
    if invalid_project_ids:
        raise ValueError(
            f"The following project IDs do not belong to account {account_id}: {invalid_project_ids}"
        )


def _get_param_value(override, field_name: str, plan_value):
    """Get parameter value from override if present, otherwise from plan."""
    if override and hasattr(override, field_name):
        override_value = getattr(override, field_name)
        if override_value is not None:
            return override_value
    return plan_value


def get_account_subscriptions(
    session: Session,
    account_id: uuid.UUID,
) -> tuple[Optional[db.AccountSubscription], list[db.AccountSubscription]]:
    """
    Get all active subscriptions for an account, separated into current and scheduled.
    Args:
        session: Database session
        account_id: Account ID to get subscriptions for
    Returns:
        Tuple of (current_subscription, scheduled_subscriptions)
    """

    account_subscription_repository = AccountSubscriptionRepository(
        session, auto_commit=False
    )
    subscriptions = account_subscription_repository.get_account_subscriptions(
        account_id
    )

    if not subscriptions:
        return None, []

    start_date = subscriptions[0].trial_start_date or subscriptions[0].start_date
    if start_date <= datetime.now(UTC):
        return subscriptions[0], subscriptions[1:]
    else:
        return None, subscriptions


def update_account_subscription(
    session: Session,
    context: UserContext,
    account_id: uuid.UUID,
    external_id: uuid.UUID,
    update_data: dict[str, Any],
    force_update: bool = False,
) -> db.AccountSubscription:
    """
    Update an account subscription by creating a new version.
    Args:
        session: Database session
        context: User context for authorization and logging
        account_id: Account id for authorization
        external_id: External ID of the subscription to update
        update_data: Fields to update
        force_update: Whether to allow updates on non-active subscriptions
    Returns:
        New version of the account subscription
    """
    account_subscription_repository = AccountSubscriptionRepository(
        session, auto_commit=False
    )

    current_subscription = account_subscription_repository.get_account_subscription(
        account_id, external_id
    )
    if not current_subscription:
        raise ValueError(f"Subscription with external_id {external_id} does not exist")

    if not current_subscription.is_valid:
        if force_update:
            logger.warning(f"Force updating account subscription {external_id}!")
        else:
            raise ValueError(
                f"Cannot update subscription with status {current_subscription.status.value}. Use force_update=true to override."
            )

    new_subscription = duplicate_row(current_subscription)

    allowed_fields = {
        "payment_method",
        "trial_start_date",
        "start_date",
        "end_date",
        "status",
        "stripe_subscription_id",
    }

    for k, v in update_data.items():
        if v is not None and k in allowed_fields:
            setattr(new_subscription, k, v)
    new_subscription.version = (new_subscription.version or 0) + 1

    account_subscription_repository.update_account_subscription_status(
        external_id, SubscriptionStatus.cancelled
    )
    with change_log_context(
        session=session,
        resource_type=ChangeResourceType.Subscription,
        author=context.email,
        account_id=account_id,
        resource_id=str(external_id),
        old_record=copy.copy(current_subscription),
        auto_commit=False,
    ) as ctx:
        new_subscription = account_subscription_repository.create_account_subscription(
            new_subscription
        )
        ctx.new_record = new_subscription

    try:
        session.commit()
    except Exception as err:
        logger.error(f"Failed to update account subscription due to error: {err}")
        raise err

    return new_subscription


def update_account_subscription_status(
    session: Session,
    context: UserContext,
    account_id: uuid.UUID,
    external_id: uuid.UUID,
    new_status: SubscriptionStatus,
) -> db.AccountSubscription:
    """
    Update the status of an account subscription.
    Args:
        session: Database session
        context: User context for authorization and logging
        account_id: Account id
        external_id: External ID of the subscription to update
        new_status: New status to set
    Returns:
        Updated account subscription
    """
    subscription_repository = AccountSubscriptionRepository(session, auto_commit=True)

    current_subscription = subscription_repository.get_account_subscription(
        account_id, external_id
    )
    if not current_subscription:
        raise ValueError(f"Subscription with external_id {external_id} does not exist")

    old_subscription = copy.copy(current_subscription)

    try:
        with change_log_context(
            session=session,
            resource_type=ChangeResourceType.Subscription,
            author=context.email,
            account_id=account_id,
            resource_id=str(external_id),
            old_record=old_subscription,
            auto_commit=False,
        ) as ctx:
            updated_subscription = (
                subscription_repository.update_account_subscription_status(
                    external_id, new_status
                )
            )
            ctx.new_record = updated_subscription
    except Exception as e:
        logger.warning(
            f"Change log failed for account subscription status update, proceeding anyway: {e}"
        )
        updated_subscription = (
            subscription_repository.update_account_subscription_status(
                external_id, new_status
            )
        )

    return updated_subscription


def cancel_account_subscription(
    session: Session,
    context: UserContext,
    account_name: str,
    external_id: uuid.UUID,
) -> Optional[db.AccountSubscription]:
    """
    Cancel an account subscription.
    Business Rules:
    - Cannot cancel free trial if there's a paid subscription in place
    - Can cancel paid subscription while keeping free trial
    - For paid subscriptions, must cancel Stripe subscription first
    Args:
        session: Database session
        context: User context for authorization and logging
        account_name: Account name for authorization
        external_id: External ID of the subscription to cancel
    Returns:
        Cancelled account subscription (if soft delete) or None (if hard delete)
    """
    account = account_service.get_account(session, account_name)
    if not account:
        raise ValueError(f"Account {account_name} does not exist")

    account_subscription_repository = AccountSubscriptionRepository(
        session, auto_commit=False
    )
    project_subscription_repository = ProjectSubscriptionRepository(
        session=session, auto_commit=False
    )

    subscription_to_cancel = account_subscription_repository.get_account_subscription(
        account.id, external_id
    )
    if not subscription_to_cancel:
        raise ValueError(f"Subscription with external_id {external_id} does not exist")

    # Cancel Stripe subscription first if it exists
    if subscription_to_cancel.stripe_subscription_id:
        stripe_cancelled = _stripe.cancel_subscription(
            subscription_to_cancel.stripe_subscription_id
        )
        if not stripe_cancelled:
            raise RuntimeError(
                f"Failed to cancel Stripe subscription {subscription_to_cancel.stripe_subscription_id}. "
                "Internal subscription will not be cancelled to maintain data consistency."
            )
        logger.info(
            "Successfully cancelled Stripe subscription",
            extra={
                "account_id": str(account.id),
                "subscription_external_id": str(external_id),
                "stripe_subscription_id": subscription_to_cancel.stripe_subscription_id,
            },
        )

    old_subscription = copy.copy(subscription_to_cancel)

    try:
        with change_log_context(
            session=session,
            resource_type=ChangeResourceType.Subscription,
            author=context.email,
            account_id=account.id,
            resource_id=str(external_id),
            old_record=old_subscription,
            auto_commit=False,
        ) as ctx:
            cancelled_subscription = (
                account_subscription_repository.update_account_subscription_status(
                    external_id,
                    SubscriptionStatus.cancelled,
                )
            )
            ctx.new_record = cancelled_subscription
    except Exception as e:
        logger.warning(
            f"Change log failed for account subscription cancellation, proceeding anyway: {e}"
        )

        cancelled_subscription = (
            account_subscription_repository.update_account_subscription_status(
                external_id,
                SubscriptionStatus.cancelled,
            )
        )

    # Cancel all the attached project subscriptions
    project_subscriptions = (
        project_subscription_repository.get_project_subscriptions_by_subscription_id(
            external_id
        )
    )
    for project_sub in project_subscriptions:
        project_subscription_repository.delete_project_subscription(
            project_sub.project_id, external_id
        )

    try:
        session.commit()
    except Exception as err:
        session.rollback()
        logger.error(
            f"Failed to cancel account subscription! Error: {err}", exc_info=True
        )
        raise err

    logger.info(
        f"Cancelled subscription for account {account_name}",
        extra={
            "account_id": str(account.id),
            "subscription_external_id": str(external_id),
            "stripe_subscription_id": subscription_to_cancel.stripe_subscription_id,
        },
    )

    return cancelled_subscription


def get_account_subscription_by_external_id(
    session: Session,
    external_id: uuid.UUID,
) -> db.AccountSubscription | None:
    account_subscription_repository = AccountSubscriptionRepository(
        session, auto_commit=True
    )
    return account_subscription_repository.get_account_subscription_by_external_id(
        external_id
    )


def create_stripe_checkout_url(
    session: Session,
    account_id: uuid.UUID,
    external_id: uuid.UUID,
    customer_email: str | None,
    redirect_url_prefix: str,
) -> str | None:
    """
    Create a Stripe checkout URL for a subscription.

    Args:
        session: Database session
        account_id: UUID of the account creating the subscription
        external_id: External ID of the subscription to create checkout for
        project_ids: List of project UUIDs to associate with the subscription
        customer_email: Optional email for the customer
        redirect_url_prefix: URL prefix for success/cancel redirects

    Returns:
        Checkout URL string or None if subscription not found
    """
    project_subscription_repo = ProjectSubscriptionRepository(session)

    # Get subscription by external_id
    subscription = get_account_subscription_by_external_id(session, external_id)

    if not subscription or subscription.account_id != account_id:
        return None

    # Validate subscription status
    if not subscription.is_valid:
        raise ValueError(f"Subscription status is invalid: {subscription.status}")

    # Validate subscription doesn't already have a Stripe subscription ID
    if subscription.stripe_subscription_id:
        raise ValueError("Subscription already has a Stripe subscription ID")

    # Get subscription plan to get the price_id
    plan = subscription.subscription_plan
    if not plan or not plan.stripe_price_id:
        raise RuntimeError(
            "Subscription plan does not have a Stripe price ID configured"
        )

    project_subscriptions = (
        project_subscription_repo.get_project_subscriptions_by_subscription_id(
            subscription.external_id
        )
    )

    # Create checkout session
    checkout_session = _stripe.create_checkout_session(
        account_id=account_id,
        customer_email=customer_email,
        subscription_external_id=subscription.external_id,
        price_id=plan.stripe_price_id,
        quantity=len(project_subscriptions),
        redirect_url_prefix=redirect_url_prefix,
        start_date=subscription.start_date,
    )

    if not checkout_session or not checkout_session.url:
        raise RuntimeError("Failed to create checkout session")

    return checkout_session.url


def get_project_subscriptions_by_subscription_external_id(
    session: Session,
    context: UserContext,
    external_id: uuid.UUID,
) -> list[db.ProjectSubscription]:
    """
    Get all project subscriptions for a given account subscription external ID.

    Args:
        session: Database session
        context: User context for authorization and logging
        external_id: External ID of the account subscription

    Returns:
        List of project subscriptions for the account subscription
    """

    project_subscription_repository = ProjectSubscriptionRepository(
        session, auto_commit=False
    )

    project_subscriptions = (
        project_subscription_repository.get_project_subscriptions_by_subscription_id(
            external_id
        )
    )

    return project_subscriptions


def create_project_subscription(
    session: Session,
    context: UserContext,
    project_id: uuid.UUID,
    subscription_id: uuid.UUID,
) -> tuple[db.ProjectSubscription, db.Project]:
    """
    Create a new project subscription.

    Args:
        session: Database session
        context: User context for authorization and logging
        project_id: ID of the project
        subscription_id: ID of the subscription

    Returns:
        Tuple of (created project subscription, project)
    """
    from services import project_service

    project_subscription_repository = ProjectSubscriptionRepository(
        session, auto_commit=False
    )

    # Validate project exists
    project = project_service.get_project(session, project_id)
    if not project:
        raise ValueError(f"Project {project_id} does not exist")

    # Validate subscription exists
    subscription = get_account_subscription_by_external_id(session, subscription_id)
    if not subscription:
        raise ValueError(f"Subscription {subscription_id} does not exist")

    # Check if project subscription already exists
    existing_project_subscription = (
        project_subscription_repository.get_project_subscription(
            project_id, subscription_id
        )
    )
    if existing_project_subscription:
        raise ValueError(
            f"Project subscription already exists for project {project_id} and subscription {subscription_id}"
        )

    # Create the project subscription
    project_subscription = project_subscription_repository.create_project_subscription(
        project_id, subscription_id
    )

    session.commit()

    # Update Stripe subscription quantity if Stripe subscription exists
    if subscription.stripe_subscription_id and subscription.subscription_plan:
        plan = subscription.subscription_plan
        if plan.stripe_price_id:
            # Get the current count of active project subscriptions
            all_project_subscriptions = project_subscription_repository.get_project_subscriptions_by_subscription_id(
                subscription_id
            )
            new_quantity = len(all_project_subscriptions)

            # Update Stripe subscription quantity
            stripe_updated = _stripe.update_subscription_quantity(
                subscription.stripe_subscription_id, plan.stripe_price_id, new_quantity
            )

            if stripe_updated:
                logger.info(
                    "Updated Stripe subscription quantity",
                    extra={
                        "subscription_id": str(subscription_id),
                        "stripe_subscription_id": subscription.stripe_subscription_id,
                        "new_quantity": new_quantity,
                    },
                )
            else:
                logger.warning(
                    "Failed to update Stripe subscription quantity",
                    extra={
                        "subscription_id": str(subscription_id),
                        "stripe_subscription_id": subscription.stripe_subscription_id,
                        "new_quantity": new_quantity,
                    },
                )

    logger.info(
        "Created project subscription",
        extra={
            "project_id": str(project_id),
            "subscription_id": str(subscription_id),
            "project_subscription_id": str(project_subscription.id),
        },
    )

    return project_subscription, project


def remove_project_subscription(
    session: Session,
    context: UserContext,
    project_id: uuid.UUID,
    subscription_id: uuid.UUID,
) -> bool:
    """
    Remove a project subscription (soft delete).

    Args:
        session: Database session
        context: User context for authorization and logging
        project_id: ID of the project
        subscription_id: ID of the subscription

    Returns:
        True if removal was successful, False otherwise
    """
    project_subscription_repository = ProjectSubscriptionRepository(
        session, auto_commit=False
    )

    # Check if project subscription exists
    project_subscription = project_subscription_repository.get_project_subscription(
        project_id, subscription_id
    )
    if not project_subscription:
        raise ValueError(
            f"Project subscription does not exist for project {project_id} and subscription {subscription_id}"
        )

    # Get subscription details for Stripe update
    subscription = get_account_subscription_by_external_id(session, subscription_id)
    if not subscription:
        raise ValueError(f"Subscription {subscription_id} does not exist")

    # Remove the project subscription
    success = project_subscription_repository.delete_project_subscription(
        project_id, subscription_id
    )

    if success:
        session.commit()

        # Update Stripe subscription quantity if Stripe subscription exists
        if subscription.stripe_subscription_id and subscription.subscription_plan:
            plan = subscription.subscription_plan
            if plan.stripe_price_id:
                # Get the current count of active project subscriptions (after removal)
                all_project_subscriptions = project_subscription_repository.get_project_subscriptions_by_subscription_id(
                    subscription_id
                )
                new_quantity = len(all_project_subscriptions)

                # Update Stripe subscription quantity
                stripe_updated = _stripe.update_subscription_quantity(
                    subscription.stripe_subscription_id,
                    plan.stripe_price_id,
                    new_quantity,
                )

                if stripe_updated:
                    logger.info(
                        "Updated Stripe subscription quantity after removal",
                        extra={
                            "subscription_id": str(subscription_id),
                            "stripe_subscription_id": subscription.stripe_subscription_id,
                            "new_quantity": new_quantity,
                        },
                    )
                else:
                    logger.warning(
                        "Failed to update Stripe subscription quantity after removal",
                        extra={
                            "subscription_id": str(subscription_id),
                            "stripe_subscription_id": subscription.stripe_subscription_id,
                            "new_quantity": new_quantity,
                        },
                    )

        logger.info(
            "Removed project subscription",
            extra={
                "project_id": str(project_id),
                "subscription_id": str(subscription_id),
                "project_subscription_id": str(project_subscription.id),
            },
        )

    return success
