import copy
import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

import db
from api.routes.admin import UserContext
from db.tables.change_log import ChangeResourceType
from db.tables.subscriptions import SubscriptionType
from services import account_service
from services.history_service import change_log_context
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

    subscription_repository = db.SubscriptionRepository(session, auto_commit=False)

    with change_log_context(
        session=session,
        resource_type=ChangeResourceType.SubscriptionPlan,
        author=context.email,
        account_id=uuid.uuid4(),
        auto_commit=True,
    ) as ctx:
        plan = subscription_repository.create_subscription_plan(
            name=params.name.strip(),
            tier=params.tier,
            **{k: v for k, v in asdict(params).items() if v is not None},
        )

        ctx.resource_id = str(plan.id)
        ctx.new_record = plan

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
    subscription_repository = db.SubscriptionRepository(session, auto_commit=False)

    existing_plan = subscription_repository.get_subscription_plan_by_id(plan_id)
    if not existing_plan:
        raise ValueError(f"Subscription plan {plan_id} does not exist.")

    old_plan = copy.copy(existing_plan)

    with change_log_context(
        session=session,
        resource_type=ChangeResourceType.SubscriptionPlan,
        author=context.email,
        account_id=existing_plan.account_id,
        resource_id=str(plan_id),
        old_record=old_plan,
        auto_commit=True,
    ) as ctx:
        updated_plan = subscription_repository.update_subscription_plan(
            plan_id,
            **{k: v for k, v in asdict(params).items() if v is not None},
        )
        ctx.new_record = updated_plan
        return updated_plan


def delete_subscription_plan(
    session: Session,
    context: UserContext,
    plan_id: uuid.UUID,
):
    """
    Delete a subscription plan by ID.

    Args:
        session: Database session
        context: User context for authorization and logging
        plan_id: Plan ID to delete

    Raises:
        ValueError: If plan cannot be deleted due to business rules
    """
    subscription_repository = db.SubscriptionRepository(session, auto_commit=False)

    existing_plan = subscription_repository.get_subscription_plan_by_id(plan_id)
    if not existing_plan:
        raise ValueError(f"Subscription plan {plan_id} does not exist.")

    with change_log_context(
        session=session,
        resource_type=ChangeResourceType.SubscriptionPlan,
        author=context.email,
        account_id=existing_plan.account_id,
        resource_id=str(plan_id),
        old_record=existing_plan,
        auto_commit=True,
    ):
        subscription_repository.delete_subscription_plan(plan_id)

        logger.info(
            f"Deleted subscription plan: {existing_plan.name}",
            extra={
                "plan_id": str(plan_id),
                "plan_name": existing_plan.name,
                "author": context.email,
            },
        )


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
