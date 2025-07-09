import copy
import uuid
from typing import Optional

from sqlalchemy.orm import Session

import db
from api.routes.admin import UserContext
from db.repositories.subscription_repository import (
    SubscriptionPlanRepository,
)
from db.tables.change_log import ChangeResourceType
from services.history_service import change_log_context
from services.subscription_service.schema import SubscriptionPlanParams
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
    if not params.tier:
        raise ValueError("Plan tier is required")

    subscription_plan_repository = SubscriptionPlanRepository(session, auto_commit=True)
    params_map = params.model_dump()

    try:
        with change_log_context(
            session=session,
            resource_type=ChangeResourceType.SubscriptionPlan,
            author=context.email,
            auto_commit=False,
        ) as ctx:
            plan = subscription_plan_repository.create_subscription_plan(**params_map)

            ctx.resource_id = str(plan.id)
            ctx.new_record = plan
    except Exception as e:
        logger.warning(
            f"Change log failed for subscription plan creation, proceeding anyway: {e}"
        )
        plan = subscription_plan_repository.create_subscription_plan(**params_map)

    logger.info(
        f"Created subscription plan: {plan.name}",
        extra=params_map,
    )
    return plan


def delete_subscription_plan(
    session: Session,
    context: UserContext,
    plan_id: uuid.UUID,
    hard_delete: bool,
):
    """
    Delete a subscription plan. A plan can only be deleted if it has no associated
    subscription plans.
    """
    subscription_plan_repository = SubscriptionPlanRepository(
        session, auto_commit=False
    )

    existing_plan = subscription_plan_repository.get_subscription_plan_by_id(plan_id)
    if not existing_plan:
        raise ValueError(f"Subscription plan {plan_id} does not exist.")

    has_subscriptions = subscription_plan_repository.has_active_account_subscriptions(
        plan_id
    )
    if has_subscriptions:
        raise ValueError(
            f"Subscription plan {plan_id} has associated subscriptions, can't be deleted."
        )

    old_plan = copy.copy(existing_plan)

    try:
        with change_log_context(
            session=session,
            resource_type=ChangeResourceType.SubscriptionPlan,
            author=context.email,
            resource_id=str(plan_id),
            old_record=old_plan,
            auto_commit=False,
        ) as ctx:
            if hard_delete:
                subscription_plan_repository.delete_subscription_plan(plan_id)
                ctx.new_record = None
            else:
                ctx.new_record = subscription_plan_repository.update_subscription_plan(
                    plan_id, active=False
                )
    except Exception as e:
        logger.warning(
            f"Change log failed for subscription plan deletion, proceeding anyway: {e}"
        )
        subscription_plan_repository.delete_subscription_plan(plan_id)


def get_subscription_plans(
    session: Session,
    hidden: Optional[bool] = None,
):
    """
    Get all subscription plans, optionally filtered by hidden status.

    Args:
        session: Database session
        hidden: Optional filter for hidden status (None = all, True = hidden only, False = not hidden only)
    """
    subscription_plan_repository = SubscriptionPlanRepository(
        session, auto_commit=False
    )
    return subscription_plan_repository.get_subscription_plans(hidden=hidden)


def update_subscription_plan(
    session: Session,
    context: UserContext,
    plan_id: uuid.UUID,
    params: SubscriptionPlanParams,
) -> db.SubscriptionPlan:
    """
    Update a subscription plan with business logic for field restrictions.

    Business Rules:
    - If there are no linked account subscriptions (deleted ones are fine), all fields can be updated
    - If there are any linked account subscriptions that are not deleted, only these fields can be updated:
      - name
      - description
      - sort_id
      - free_trial_days
      - active
      - hidden

    Args:
        session: Database session
        context: User context for authorization and logging
        plan_id: Plan ID to update
        params: Subscription plan parameters to update

    Returns:
        Updated subscription plan

    Raises:
        ValueError: If plan not found or if restricted fields are being updated when there are active subscriptions
    """
    subscription_plan_repository = SubscriptionPlanRepository(session, auto_commit=True)

    existing_plan = subscription_plan_repository.get_subscription_plan_by_id(plan_id)
    if not existing_plan:
        raise ValueError(f"Subscription plan {plan_id} does not exist.")

    # Check if there are active account subscriptions linked to this plan
    has_active_subscriptions = (
        subscription_plan_repository.has_active_account_subscriptions(plan_id)
    )

    # Define which fields are allowed when there are active subscriptions
    restricted_update_fields = {
        "name",
        "description",
        "sort_id",
        "free_trial_days",
        "active",
        "hidden",
    }

    # Get the fields that are being updated (non-None values in params)
    update_data = {}
    for field, value in params.model_dump().items():
        if value is not None:
            update_data[field] = value

    # If there are active subscriptions, check field restrictions
    if has_active_subscriptions:
        restricted_fields = set(update_data.keys()) - restricted_update_fields
        if restricted_fields:
            raise ValueError(
                f"Cannot update fields {restricted_fields} because there are active account subscriptions linked to this plan. "
                f"Only these fields can be updated: {restricted_update_fields}"
            )

    old_plan = copy.copy(existing_plan)

    try:
        with change_log_context(
            session=session,
            resource_type=ChangeResourceType.SubscriptionPlan,
            author=context.email,
            resource_id=str(plan_id),
            old_record=old_plan,
            auto_commit=False,
        ) as ctx:
            updated_plan = subscription_plan_repository.update_subscription_plan(
                plan_id, **update_data
            )
            ctx.new_record = updated_plan
    except Exception as e:
        logger.warning(
            f"Change log failed for subscription plan update, proceeding anyway: {e}"
        )

        updated_plan = subscription_plan_repository.update_subscription_plan(
            plan_id, **update_data
        )

    if not updated_plan:
        raise ValueError(f"Failed to update subscription plan {plan_id}")

    logger.info(
        f"Updated subscription plan: {updated_plan.name}",
        extra={
            "plan_id": str(plan_id),
            "plan_name": updated_plan.name,
            "updated_fields": list(update_data.keys()),
            "has_active_subscriptions": has_active_subscriptions,
            "author": context.email,
        },
    )

    return updated_plan


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
