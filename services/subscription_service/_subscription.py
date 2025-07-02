import copy
import uuid
from datetime import UTC, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

import db
from api.routes.admin import UserContext
from db.tables.change_log import ChangeResourceType
from db.tables.subscriptions import SubscriptionStatus, SubscriptionType
from services import account_service
from services.history_service import change_log_context
from services.subscription_service import _stripe
from services.subscription_service.schema import (
    SubscriptionParams,
    SubscriptionPlanParams,
)
from utils.log import logger


def create_subscription_plan(
    session: Session,
    context: UserContext,
    params: SubscriptionPlanParams,
) -> db.SubscriptionPlan:
    """
    Create a new subscription plan.

    Args:
        session: Database session
        context: User context for authorization and logging
        params: Subscription plan parameters

    Returns:
        Created subscription plan
    """

    if not params.name or not params.name.strip():
        raise ValueError("Plan name is required")

    subscription_repository = db.SubscriptionRepository(session, auto_commit=True)

    try:
        with change_log_context(
            session=session,
            resource_type=ChangeResourceType.SubscriptionPlan,
            account_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
            author=context.email,
            auto_commit=False,
        ) as ctx:
            plan = subscription_repository.create_subscription_plan(
                name=params.name.strip(),
                tier=params.tier,
                **{
                    k: v
                    for k, v in params.model_dump().items()
                    if v is not None and k not in ["name", "tier"]
                },
            )

            ctx.resource_id = str(plan.id)
            ctx.new_record = plan
    except Exception as e:
        logger.warning(
            f"Change log failed for subscription plan creation, proceeding anyway: {e}"
        )

        plan = subscription_repository.create_subscription_plan(
            name=params.name.strip(),
            tier=params.tier,
            **{
                k: v
                for k, v in params.model_dump().items()
                if v is not None and k not in ["name", "tier"]
            },
        )

    logger.info(
        f"Created subscription plan: {plan.name}",
        extra={
            "plan_id": str(plan.id),
            "plan_name": plan.name,
            "tier": plan.tier.value,
            "active": plan.active,
            "author": context.email,
        },
    )

    return plan


def update_subscription_plan(
    session: Session,
    context: UserContext,
    plan_id: uuid.UUID,
    params: SubscriptionPlanParams,
) -> db.SubscriptionPlan:
    """
    Update an existing subscription plan.

    Args:
        session: Database session
        context: User context for authorization and logging
        plan_id: Plan ID to update
        params: Updated subscription plan parameters

    Returns:
        Updated subscription plan
    """
    subscription_repository = db.SubscriptionRepository(session, auto_commit=True)

    existing_plan = subscription_repository.get_subscription_plan_by_id(plan_id)
    if not existing_plan:
        raise ValueError(f"Subscription plan {plan_id} does not exist.")

    old_plan = copy.copy(existing_plan)

    try:
        with change_log_context(
            session=session,
            resource_type=ChangeResourceType.SubscriptionPlan,
            author=context.email,
            account_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
            resource_id=str(plan_id),
            old_record=old_plan,
            auto_commit=False,
        ) as ctx:
            updated_plan = subscription_repository.update_subscription_plan(
                plan_id,
                **{
                    k: v
                    for k, v in params.model_dump().items()
                    if v is not None and k not in ["name", "tier"]
                },
            )
            ctx.new_record = updated_plan
    except Exception as e:
        logger.warning(
            f"Change log failed for subscription plan update, proceeding anyway: {e}"
        )

        updated_plan = subscription_repository.update_subscription_plan(
            plan_id,
            **{
                k: v
                for k, v in params.model_dump().items()
                if v is not None and k not in ["name", "tier"]
            },
        )

    return updated_plan


def expire_subscription_plan(
    session: Session,
    context: UserContext,
    plan_id: uuid.UUID,
    hard_delete: bool = False,
) -> Optional[db.SubscriptionPlan]:
    """
    Expire or hard delete a subscription plan by ID.

    Args:
        session: Database session
        context: User context for authorization and logging
        plan_id: Plan ID to expire or hard delete
        hard_delete: Whether to permanently delete the plan from the database

    Returns:
        Expired subscription plan or None if hard delete is True

    Raises:
        ValueError: If plan cannot be expired due to business rules
    """
    subscription_repository = db.SubscriptionRepository(session, auto_commit=True)

    existing_plan = subscription_repository.get_subscription_plan_by_id(plan_id)
    if not existing_plan:
        raise ValueError(f"Subscription plan {plan_id} does not exist.")

    old_plan = copy.copy(existing_plan)

    try:
        with change_log_context(
            session=session,
            resource_type=ChangeResourceType.SubscriptionPlan,
            author=context.email,
            account_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
            resource_id=str(plan_id),
            old_record=old_plan,
            auto_commit=False,
        ) as ctx:
            expired_plan = subscription_repository.expire_subscription_plan(
                plan_id, hard_delete
            )
            if hard_delete:
                ctx.new_record = None
            else:
                ctx.new_record = expired_plan
    except Exception as e:
        logger.warning(
            f"Change log failed for subscription plan {'deletion' if hard_delete else 'expiration'}, proceeding anyway: {e}"
        )

        expired_plan = subscription_repository.expire_subscription_plan(
            plan_id, hard_delete
        )

    return expired_plan


def get_subscription_plans(
    session: Session,
):
    """
    Get all subscription plans.
    """
    subscription_repository = db.SubscriptionRepository(session, auto_commit=False)
    return subscription_repository.get_subscription_plans()


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
    subscription_repository = db.SubscriptionRepository(session, auto_commit=False)
    return subscription_repository.get_subscription_plan_by_id(plan_id)


def _validate_subscription_request(params: SubscriptionParams, account, plan):
    """Validate subscription request parameters."""
    if not params.subscription_plan_id:
        raise ValueError("Missing subscription_plan_id in request")

    if not plan:
        raise ValueError(f"Subscription plan '{params.subscription_plan_id}' not found")

    if not plan.active:
        raise ValueError("Cannot create subscription for inactive plan")

    if params.subscription_type == SubscriptionType.contract:
        _validate_contract_overrides(params.override)


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
    return {
        "call_quota": _get_param_value(params.override, "call_quota", plan.call_quota),
        "order_quota": _get_param_value(
            params.override, "order_quota", plan.order_quota
        ),
        "call_overage_charge": _get_param_value(
            params.override, "call_overage_charge", plan.call_overage_charge
        ),
        "order_overage_charge": _get_param_value(
            params.override, "order_overage_charge", plan.order_overage_charge
        ),
        "monthly_fee": _get_param_value(
            params.override, "monthly_fee", plan.monthly_fee
        ),
        "stripe_subscription_id": _get_param_value(
            params.override, "stripe_subscription_id", None
        ),
    }


def _get_plan_by_id(subscription_repository, params: SubscriptionParams):
    """Get and validate subscription plan by ID."""
    try:
        plan_id = uuid.UUID(params.subscription_plan_id)
    except ValueError:
        raise ValueError("Invalid subscription plan ID format")

    return subscription_repository.get_subscription_plan_by_id(plan_id)


def create_subscription(
    session: Session,
    context: UserContext,
    account_name: str,
    params: SubscriptionParams,
) -> db.AccountSubscription:
    """
    Create a new account subscription according to the specification.

    Business Logic:
    - If any field is present in the override, use that, otherwise calculate according to logic
    - If subscription type is contract, everything must be listed in the override section
    - Cannot create new subscription if start_date and end_date overlaps with existing active subscription of same type
    - New subscription always has 'active' status

    Date Logic:
    - Trial start_date: now
    - Monthly start_date: end_date of last free trial (if exists), otherwise now
    - Trial end_date: start_date + free_trial_days from plan
    - Monthly end_date: start_date + 24 months
    """

    account = account_service.get_account(session, account_name)
    if not account:
        raise ValueError(f"Account {account_name} does not exist")

    subscription_repository = db.SubscriptionRepository(session, auto_commit=False)

    plan = _get_plan_by_id(subscription_repository, params)
    _validate_subscription_request(params, account, plan)

    assert plan is not None

    start_date = _calculate_start_date(
        subscription_repository, account.id, params, plan
    )
    end_date = _calculate_end_date(start_date, params, plan)

    if subscription_repository.check_subscription_overlap(
        account.id, params.subscription_type, start_date, end_date
    ):
        raise ValueError(
            f"Cannot create subscription: overlaps with existing active {params.subscription_type.value} subscription"
        )

    subscription_params = _extract_subscription_parameters(params, plan)

    with change_log_context(
        session=session,
        resource_type=ChangeResourceType.Subscription,
        author=context.email,
        account_id=account.id,
        auto_commit=True,
    ) as ctx:
        subscription = subscription_repository.create_account_subscription(
            account_id=account.id,
            subscription_plan_id=plan.id,
            subscription_type=params.subscription_type,
            start_date=start_date,
            end_date=end_date,
            **subscription_params,
        )

        ctx.resource_id = str(subscription.id)
        ctx.new_record = subscription

        logger.info(
            f"Created subscription for account {account_name}",
            extra={
                "account_id": str(account.id),
                "subscription_id": str(subscription.id),
                "subscription_type": params.subscription_type.value,
                "plan_id": str(plan.id),
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
        )

    return subscription


def _calculate_start_date(
    repo: db.SubscriptionRepository,
    account_id: uuid.UUID,
    params: SubscriptionParams,
    plan,
) -> datetime:
    """Calculate the start date based on subscription type and override."""
    if params.override and params.override.start_date:
        return params.override.start_date

    now = datetime.now(UTC)

    if params.subscription_type == SubscriptionType.trial:
        return now

    elif params.subscription_type == SubscriptionType.monthly:
        last_trial = repo.get_last_trial_subscription(account_id)
        if last_trial:
            return last_trial.end_date
        else:
            return now

    else:
        return now


def _calculate_end_date(
    start_date: datetime, params: SubscriptionParams, plan
) -> datetime:
    """Calculate the end date based on subscription type and override."""
    if params.override and params.override.end_date:
        return params.override.end_date

    if params.subscription_type == SubscriptionType.trial:
        if plan.free_trial_days:
            return start_date + timedelta(days=plan.free_trial_days)
        else:
            return start_date + timedelta(days=7)

    elif params.subscription_type == SubscriptionType.monthly:
        return start_date.replace(year=start_date.year + 2)

    else:
        return start_date + timedelta(days=365 * 2)


def _get_param_value(override, field_name: str, plan_value):
    """Get parameter value from override if present, otherwise from plan."""
    if override and hasattr(override, field_name):
        override_value = getattr(override, field_name)
        if override_value is not None:
            return override_value
    return plan_value


def get_account_subscriptions(
    session: Session,
    account_name: str,
) -> tuple[Optional[db.AccountSubscription], list[db.AccountSubscription]]:
    """
    Get all active subscriptions for an account, separated into current and scheduled.
    Args:
        session: Database session
        account_name: Account name to get subscriptions for
    Returns:
        Tuple of (current_subscription, scheduled_subscriptions)
    """
    account = account_service.get_account(session, account_name)
    if not account:
        raise ValueError(f"Account {account_name} does not exist")

    subscription_repository = db.SubscriptionRepository(session, auto_commit=False)
    subscriptions = subscription_repository.get_account_subscriptions(account.id)

    now = datetime.now(UTC)
    current_subscription = None
    scheduled_subscriptions = []

    for subscription in subscriptions:
        if subscription.start_date <= now <= subscription.end_date:
            current_subscription = subscription
        elif subscription.start_date > now:
            scheduled_subscriptions.append(subscription)

    scheduled_subscriptions.sort(key=lambda s: s.start_date)

    return current_subscription, scheduled_subscriptions


def update_account_subscription(
    session: Session,
    context: UserContext,
    account_name: str,
    external_id: uuid.UUID,
    request_data: dict,
    force_update: bool = False,
) -> db.AccountSubscription:
    """
    Update an account subscription by creating a new version.
    Args:
        session: Database session
        context: User context for authorization and logging
        account_name: Account name for authorization
        external_id: External ID of the subscription to update
        request_data: Fields to update
        force_update: Whether to allow updates on non-active subscriptions
    Returns:
        New version of the account subscription
    """
    account = account_service.get_account(session, account_name)
    if not account:
        raise ValueError(f"Account {account_name} does not exist")

    subscription_repository = db.SubscriptionRepository(session, auto_commit=True)

    current_subscription = (
        subscription_repository.get_account_subscription_by_external_id(external_id)
    )
    if not current_subscription:
        raise ValueError(f"Subscription with external_id {external_id} does not exist")

    if current_subscription.account_id != account.id:
        raise ValueError(
            f"Subscription {external_id} does not belong to account {account_name}"
        )

    if current_subscription.status != SubscriptionStatus.active and not force_update:
        raise ValueError(
            f"Cannot update subscription with status {current_subscription.status.value}. Use force_update=true to override."
        )

    old_subscription = copy.copy(current_subscription)

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
            new_subscription = subscription_repository.create_subscription_version(
                current_subscription, **request_data
            )
            ctx.new_record = new_subscription
    except Exception as e:
        logger.warning(
            f"Change log failed for account subscription update, proceeding anyway: {e}"
        )

        new_subscription = subscription_repository.create_subscription_version(
            current_subscription, **request_data
        )

    return new_subscription


def update_account_subscription_status(
    session: Session,
    context: UserContext,
    account_name: str,
    external_id: uuid.UUID,
    new_status: SubscriptionStatus,
) -> db.AccountSubscription:
    """
    Update the status of an account subscription.
    Args:
        session: Database session
        context: User context for authorization and logging
        account_name: Account name for authorization
        external_id: External ID of the subscription to update
        new_status: New status to set
    Returns:
        Updated account subscription
    """
    account = account_service.get_account(session, account_name)
    if not account:
        raise ValueError(f"Account {account_name} does not exist")

    subscription_repository = db.SubscriptionRepository(session, auto_commit=True)

    current_subscription = (
        subscription_repository.get_account_subscription_by_external_id(external_id)
    )

    if not current_subscription:
        raise ValueError(f"Subscription with external_id {external_id} does not exist")

    if current_subscription.account_id != account.id:
        raise ValueError(
            f"Subscription {external_id} does not belong to account {account_name}"
        )

    old_subscription = copy.copy(current_subscription)

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
    hard_delete: bool = False,
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
        hard_delete: Whether to permanently delete the subscription from the database
    Returns:
        Cancelled account subscription (if soft delete) or None (if hard delete)
    """
    account = account_service.get_account(session, account_name)
    if not account:
        raise ValueError(f"Account {account_name} does not exist")

    subscription_repository = db.SubscriptionRepository(session, auto_commit=True)

    subscription_to_cancel = (
        subscription_repository.get_account_subscription_by_external_id(external_id)
    )
    if not subscription_to_cancel:
        raise ValueError(f"Subscription with external_id {external_id} does not exist")

    if subscription_to_cancel.account_id != account.id:
        raise ValueError(
            f"Subscription {external_id} does not belong to account {account_name}"
        )

    if not hard_delete and subscription_to_cancel.status not in [
        SubscriptionStatus.active,
        SubscriptionStatus.pending,
    ]:
        raise ValueError(
            f"Cannot cancel subscription with status {subscription_to_cancel.status.value}"
        )

    if not hard_delete:
        active_subscriptions = subscription_repository.get_account_active_subscriptions(
            account.id
        )

        if subscription_to_cancel.subscription_type == SubscriptionType.trial:
            paid_subscriptions = [
                sub
                for sub in active_subscriptions
                if sub.subscription_type
                in [SubscriptionType.monthly, SubscriptionType.contract]
                and sub.external_id != external_id
            ]

            if paid_subscriptions:
                raise ValueError(
                    "Cannot cancel free trial while paid subscription is active"
                )

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
            auto_commit=True,
        ) as ctx:
            cancelled_subscription = (
                subscription_repository.cancel_account_subscription(
                    external_id, hard_delete
                )
            )
            if hard_delete:
                ctx.new_record = None
            else:
                ctx.new_record = cancelled_subscription
    except Exception as e:
        logger.warning(
            f"Change log failed for account subscription {'deletion' if hard_delete else 'cancellation'}, proceeding anyway: {e}"
        )

        cancelled_subscription = subscription_repository.cancel_account_subscription(
            external_id, hard_delete
        )

    logger.info(
        f"{'Deleted' if hard_delete else 'Cancelled'} subscription for account {account_name}",
        extra={
            "account_id": str(account.id),
            "subscription_external_id": str(external_id),
            "subscription_type": subscription_to_cancel.subscription_type.value,
            "stripe_subscription_id": subscription_to_cancel.stripe_subscription_id,
            "hard_delete": hard_delete,
        },
    )

    return cancelled_subscription


def get_account_subscription_by_external_id(
    session: Session,
    external_id: uuid.UUID,
) -> db.AccountSubscription | None:
    subscription_repository = db.SubscriptionRepository(session, auto_commit=True)
    return subscription_repository.get_account_subscription_by_external_id(external_id)


def create_checkout_url(
    session: Session,
    account_id: uuid.UUID,
    external_id: uuid.UUID,
    project_ids: list[uuid.UUID],
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
    # Can't bill a subscription that has 0 projects
    if not project_ids:
        raise ValueError("Account has no projects to associate with the subscription")

    # Get subscription by external_id
    subscription = get_account_subscription_by_external_id(session, external_id)

    if not subscription or subscription.account_id != account_id:
        return None

    # Validate subscription must be pending
    if subscription.status != SubscriptionStatus.pending:
        raise ValueError(
            f"Subscription status must be pending, but is {subscription.status}"
        )

    # Validate subscription doesn't already have a Stripe subscription ID
    if subscription.stripe_subscription_id:
        raise ValueError("Subscription already has a Stripe subscription ID")

    # Get subscription plan to get the price_id
    plan = subscription.subscription_plan
    if not plan or not plan.stripe_price_id:
        raise RuntimeError(
            "Subscription plan does not have a Stripe price ID configured"
        )

    # Create checkout session
    checkout_session = _stripe.create_checkout_session(
        account_id=account_id,
        project_ids=project_ids,
        customer_email=customer_email,
        price_id=plan.stripe_price_id,
        redirect_url_prefix=redirect_url_prefix,
        start_date=subscription.start_date,
    )

    if not checkout_session or not checkout_session.url:
        raise RuntimeError("Failed to create checkout session")

    return checkout_session.url
