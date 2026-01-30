import copy
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from typing import Any, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import db
from db import ConversationRepositoryAsync
from db.repositories.subscription_repository import (
    AccountSubscriptionRepository,
    AsyncAccountSubscriptionRepository,
    ProjectSubscriptionRepository,
    SubscriptionPlanRepository,
)
from db.tables.accounts import OnboardingMethod
from db.tables.change_log import ChangeResourceType
from db.tables.subscriptions import SubscriptionStatus
from db.tables.types import PaymentMethod
from services import account_service, project_service
from services.account_service import AccountParams
from services.auth_types import UserContext
from services.history_service import change_log_context
from services.notification_service import (
    BillingEvent,
    BillingEventType,
    handle_billing_event_sync,
)
from services.subscription_service import (
    _stripe_customer,
    _stripe_product,
    _stripe_subscription,
)
from services.subscription_service._stripe_customer import CustomerInfo
from services.subscription_service._stripe_product import MeterTier
from services.subscription_service.schema import (
    StripeCheckoutResponse,
    SubscriptionParams,
)
from utils.log import logger


def _send_subscription_activated_notification(
    session: Session,
    account: db.Account,
    subscription: db.AccountSubscription,
    plan: db.SubscriptionPlan,
) -> None:
    """Send subscription activated notification."""
    try:
        # Calculate trial end date from subscription's trial_start_date + plan's free_trial_days
        trial_end_formatted = None
        if subscription.trial_start_date and plan.free_trial_days:
            trial_end = subscription.trial_start_date + timedelta(
                days=plan.free_trial_days
            )
            trial_end_formatted = trial_end.strftime("%B %d, %Y")

        event = BillingEvent(
            type=BillingEventType.SUBSCRIPTION_ACTIVATED,
            account_id=account.id,
            payload={
                "plan_name": plan.name,
                "price": float(plan.monthly_fee or 0) / 100,  # Convert cents to dollars
                "currency": "USD",
                "trial_end": trial_end_formatted,
            },
        )
        handle_billing_event_sync(session, event)
    except Exception as e:
        logger.warning(
            f"Failed to send subscription activated notification: {e}",
            extra={
                "account_id": str(account.id),
                "subscription_id": str(subscription.id),
            },
        )


def _send_subscription_cancelled_notification(
    session: Session,
    account: db.Account,
    subscription: db.AccountSubscription,
    plan: db.SubscriptionPlan,
) -> None:
    """Send subscription cancelled notification."""
    try:
        # Calculate cancellation effective date
        cancel_date = subscription.end_date or datetime.now(UTC)
        event = BillingEvent(
            type=BillingEventType.SUBSCRIPTION_CANCELLED,
            account_id=account.id,
            payload={
                "plan_name": plan.name,
                "cancel_effective_date": cancel_date.strftime("%B %d, %Y"),
            },
        )
        handle_billing_event_sync(session, event)
    except Exception as e:
        logger.warning(
            f"Failed to send subscription cancelled notification: {e}",
            extra={
                "account_id": str(account.id),
                "subscription_id": str(subscription.id),
            },
        )


def handle_stripe_checkout_success(
    session: Session,
    context: UserContext,
    session_id: str,
) -> StripeCheckoutResponse | None:
    response = _stripe_subscription.handle_checkout_success(session_id)
    if not response:
        return response

    # Route to appropriate handler based on subscription type
    if response.subscription_type == "project":
        return _handle_project_stripe_checkout_success(session, context, response)
    else:
        return _handle_account_stripe_checkout_success(session, context, response)


def _handle_account_stripe_checkout_success(
    session: Session,
    context: UserContext,
    response: StripeCheckoutResponse,
) -> StripeCheckoutResponse:
    """Handle checkout success for account-level subscriptions."""
    data = {
        "stripe_subscription_id": response.stripe_subscription_id,
        "status": SubscriptionStatus.active,
    }
    updated_subscription = update_account_subscription(
        session,
        context,
        response.account_id,
        response.subscription_external_id,
        data,
        force_update=True,
    )
    logger.info(
        "Successfully updated account subscription's stripe id",
        extra={
            "account_subscription_id": response.subscription_external_id,
            "stripe_subscription_id": response.stripe_subscription_id,
        },
    )

    # Grant credit based on plan's credit_amount upon activation
    try:
        if (
            updated_subscription
            and updated_subscription.subscription_plan
            and updated_subscription.subscription_plan.credit_amount
        ):
            account = account_service.get_account_by_id(session, response.account_id)
            if account and account.stripe_customer_id:
                credit_amount = updated_subscription.subscription_plan.credit_amount
                grant_credit_to_account(
                    account=account,
                    credit_amount_cents=credit_amount,
                    currency="usd",
                    description=f"Plan activation credit: {updated_subscription.subscription_plan.name}",
                    issued_by="system",
                    metadata={
                        "issued_via": "stripe_checkout_success",
                        "request_source": "plan_activation",
                        "plan_name": updated_subscription.subscription_plan.name,
                    },
                )
            else:
                logger.warning(
                    "Cannot grant credit: account not found or no stripe customer ID",
                    extra={"account_id": str(response.account_id)},
                )
    except Exception as e:
        logger.error(
            "Failed to grant plan activation credit",
            extra={
                "account_id": str(response.account_id),
                "subscription_id": str(response.subscription_external_id),
                "error": str(e),
            },
            exc_info=True,
        )

    return response


def _handle_project_stripe_checkout_success(
    session: Session,
    context: UserContext,
    response: StripeCheckoutResponse,
) -> StripeCheckoutResponse:
    """Handle checkout success for project-level subscriptions."""
    if not response.project_id:
        logger.error(
            "Project ID missing from checkout response for project subscription",
            extra={"external_id": str(response.subscription_external_id)},
        )
        raise ValueError("Project ID required for project subscription checkout")

    # Get the project subscription
    project_subscription_repo = ProjectSubscriptionRepository(session)
    project_subscription = (
        project_subscription_repo.get_project_subscription_by_external_id(
            response.subscription_external_id
        )
    )

    if not project_subscription:
        logger.error(
            "Project subscription not found",
            extra={"external_id": str(response.subscription_external_id)},
        )
        raise ValueError(
            f"Project subscription {response.subscription_external_id} not found"
        )

    # Determine status based on trial
    if project_subscription.trial_start_date:
        status = SubscriptionStatus.trialing
    else:
        status = SubscriptionStatus.active

    # Update project subscription with Stripe ID and status directly (no versioning)
    # We use the repository method directly to avoid creating a new version
    updated_subscription = project_subscription_repo.update_project_subscription(
        id=project_subscription.id,
        stripe_subscription_id=response.stripe_subscription_id,
        status=status,
    )

    if not updated_subscription:
        raise ValueError(
            f"Failed to update project subscription {response.subscription_external_id}"
        )

    session.commit()

    logger.info(
        "Successfully updated project subscription's stripe id",
        extra={
            "project_id": str(response.project_id),
            "project_subscription_external_id": str(response.subscription_external_id),
            "stripe_subscription_id": response.stripe_subscription_id,
            "status": status.value,
        },
    )

    # Grant credit based on plan's credit_amount upon activation (if applicable)
    try:
        if updated_subscription and updated_subscription.subscription_plan_id:
            subscription_plan_repo = SubscriptionPlanRepository(session)
            plan = subscription_plan_repo.get_subscription_plan_by_id(
                updated_subscription.subscription_plan_id
            )

            if plan and plan.credit_amount:
                account = account_service.get_account_by_id(
                    session, response.account_id
                )
                if account and account.stripe_customer_id:
                    credit_amount = plan.credit_amount
                    grant_credit_to_account(
                        account=account,
                        credit_amount_cents=credit_amount,
                        currency="usd",
                        description=f"Plan activation credit: {plan.name}",
                        issued_by="system",
                        metadata={
                            "issued_via": "stripe_checkout_success",
                            "request_source": "project_plan_activation",
                            "plan_name": plan.name,
                            "project_id": str(response.project_id),
                        },
                    )
                else:
                    logger.warning(
                        "Cannot grant credit: account not found or no stripe customer ID",
                        extra={"account_id": str(response.account_id)},
                    )
    except Exception as e:
        logger.error(
            "Failed to grant plan activation credit for project subscription",
            extra={
                "project_id": str(response.project_id),
                "subscription_id": str(response.subscription_external_id),
                "error": str(e),
            },
            exc_info=True,
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
    """Extract subscription parameters from override or plan defaults.

    If no end_date is specified, defaults to None (ongoing subscription until cancelled).
    """
    now = datetime.now(UTC)
    default_start = now + timedelta(days=plan.free_trial_days or 0)
    default_end = None
    return {
        "trial_start_date": _get_param_value(params.schedule, "trial_start_date", now),
        "start_date": _get_param_value(params.schedule, "start_date", default_start),
        "end_date": _get_param_value(params.schedule, "end_date", default_end),
    }


def create_account_subscription(
    session: Session,
    context: UserContext,
    account: db.Account,
    params: SubscriptionParams,
    projects: List[db.Project],
) -> db.AccountSubscription:
    """
    Create a new account subscription according to the specification.

    Business Logic:
    - If any field is present in the override, use that, otherwise calculate according to logic
    - If subscription type is contract, everything must be listed in the override section
    - Cannot create new subscription if start_date and end_date overlaps with existing active subscription of same type
    - New subscription always has 'active' status
    - If projects are provided, create ProjectSubscription entries for each project

    Date Logic:
    - Trial start_date: now
    - Monthly start_date: end_date of last free trial (if exists), otherwise now
    - Trial end_date: start_date + free_trial_days from plan
    - Monthly end_date: None by default (ongoing subscription until cancelled)
    """
    subscription_plan_repository = SubscriptionPlanRepository(session)
    account_subscription_repository = AccountSubscriptionRepository(
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
        account_id=account.id,
        subscription_plan_id=plan.id,
        status=SubscriptionStatus.pending,
        payment_method=params.payment_method,
        **subscription_params,
    )

    if account_subscription_repository.check_subscription_overlap(
        account.id,
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
        account_id=account.id,
        auto_commit=False,
    ) as ctx:
        subscription = account_subscription_repository.create_account_subscription(
            account_subscription
        )
        ctx.resource_id = str(subscription.external_id)
        ctx.new_record = subscription

    logger.info(
        f"Created subscription for account {account.id}",
        extra={
            "account_id": str(account.id),
            "subscription_id": str(subscription.id),
            "plan_id": str(plan.id),
            "project_ids": [str(p.id) for p in projects],
            "trial_start_date": (
                subscription.trial_start_date.isoformat()
                if subscription.trial_start_date
                else None
            ),
            "start_date": subscription.start_date.isoformat(),
            "end_date": (
                subscription.end_date.isoformat() if subscription.end_date else None
            ),
        },
    )

    account_service.update_account(
        session,
        context,
        account.name,
        AccountParams(current_subscription_id=subscription.external_id),
    )

    for project in projects:
        add_project_to_subscription(session, account_subscription, project)

    # Send subscription activated notification
    _send_subscription_activated_notification(session, account, subscription, plan)

    return subscription


def add_project_to_subscription(
    session: Session, subscription: db.AccountSubscription, project: db.Project
) -> db.ProjectSubscription:
    subscription_plan_repository = SubscriptionPlanRepository(session)
    project_subscription_repository = ProjectSubscriptionRepository(
        session, auto_commit=False
    )

    plan = subscription_plan_repository.get_subscription_plan_by_id(
        subscription.subscription_plan_id
    )
    if not plan:
        raise ValueError("Subscription Plan not found.")

    account_name = (
        project.account.name
        if hasattr(project, "account") and project.account
        else "Unknown Account"
    )

    stripe_product_id = _stripe_product.create_product_for_project(
        project, account_name, plan.name
    )

    project_subscription = project_subscription_repository.create_project_subscription(
        project.id,
        subscription.external_id,
        stripe_product_id=stripe_product_id,
    )

    # Setup base fee
    if plan.monthly_fee and plan.monthly_fee > 0:
        base_price_id = _stripe_product.create_product_price(
            stripe_product_id,
            nickname=f"Flat fee - {project.display_name}",
            project=project,
            flat_fee=plan.monthly_fee,
        )
        project_subscription_repository.update_project_subscription(
            id=project_subscription.id,
            base_price_id=base_price_id,
        )
        if subscription.stripe_subscription_id:
            _stripe_subscription.add_subscription_item(
                subscription.stripe_subscription_id,
                base_price_id,
            )
    else:
        logger.info(
            "Subscription plan has no monthly fee, skipping base price creation"
        )

    # Setup call price
    call_meter_id = _stripe_product.create_billing_meter(
        f"{project.name} calls",
        _stripe_product.get_call_meter_event_name(project.id),
    )
    call_price_id = _stripe_product.create_product_price(
        stripe_product_id,
        nickname=f"Calls - {project.display_name}",
        project=project,
        meter_tiers=_build_call_tiers(plan),
        meter_id=call_meter_id,
    )
    project_subscription_repository.update_project_subscription(
        id=project_subscription.id,
        call_price_id=call_price_id,
    )
    if subscription.stripe_subscription_id:
        _stripe_subscription.add_subscription_item(
            subscription.stripe_subscription_id,
            call_price_id,
        )

    # Setup order price if a charge is configured
    if plan.order_overage_charge and plan.order_overage_charge > 0:
        order_meter_id = _stripe_product.create_billing_meter(
            f"{project.name} orders",
            _stripe_product.get_order_meter_event_name(project.id),
        )
        order_price_id = _stripe_product.create_product_price(
            stripe_product_id,
            nickname=f"Orders - {project.display_name}",
            meter_tiers=_build_order_tiers(plan),
            project=project,
            meter_id=order_meter_id,
        )
        project_subscription_repository.update_project_subscription(
            id=project_subscription.id,
            order_price_id=order_price_id,
        )
        if subscription.stripe_subscription_id:
            _stripe_subscription.add_subscription_item(
                subscription.stripe_subscription_id,
                order_price_id,
            )

    logger.info(
        "Created project subscription",
        extra={
            "project_id": str(project.id),
            "subscription_id": str(subscription.external_id),
            "project_subscription_id": str(project_subscription.id),
        },
    )
    return project_subscription


def _build_call_tiers(plan: db.SubscriptionPlan):
    has_call_quota = plan.call_quota and plan.call_quota > 0
    tiers = [
        MeterTier(
            last_unit=plan.call_quota,
            # if has a quota, then base tier usage is covered and should be free
            per_unit=0 if has_call_quota else (plan.call_overage_charge or 0),
        )
    ]
    if has_call_quota:
        tiers.append(
            MeterTier(
                last_unit=None,
                per_unit=plan.call_overage_charge,
            )
        )
    return tiers


def _build_order_tiers(plan: db.SubscriptionPlan):
    has_order_quota = plan.order_quota and plan.order_quota > 0
    tiers = [
        MeterTier(
            last_unit=plan.order_quota,
            # if has a quota, then base tier usage is covered and should be free
            per_unit=0 if has_order_quota else (plan.order_overage_charge or 0),
        )
    ]
    if has_order_quota:
        tiers.append(
            MeterTier(
                last_unit=None,
                per_unit=plan.order_overage_charge,
            )
        )
    return tiers


def _get_param_value(override, field_name: str, plan_value):
    """Get parameter value from override if present, otherwise from plan."""
    if override and hasattr(override, field_name):
        override_value = getattr(override, field_name)
        if override_value is not None:
            return override_value
    return plan_value


def get_current_subscription(
    session: Session, account: db.Account
) -> Optional[db.AccountSubscription]:
    if account.current_subscription_id is None:
        return None
    subscription = get_account_subscription(
        session, account.id, account.current_subscription_id
    )
    if not subscription:
        logger.error(
            "Referenced subscription does not exist, account data is polluted!",
            extra={
                "account_id": account.id,
                "subscription_external_id": account.current_subscription_id,
            },
        )
    return subscription


async def get_current_subscription_async(
    session: AsyncSession, account: db.Account
) -> Optional[db.AccountSubscription]:
    if account.current_subscription_id is None:
        return None

    repository = AsyncAccountSubscriptionRepository(session)
    subscription = await repository.get_account_subscription(
        account.id, account.current_subscription_id
    )

    if not subscription:
        logger.error(
            "Referenced subscription does not exist, account data is polluted!",
            extra={
                "account_id": account.id,
                "subscription_external_id": account.current_subscription_id,
            },
        )
    return subscription


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
            status_value = (
                current_subscription.status.value
                if current_subscription.status
                else "unknown"
            )
            raise ValueError(
                f"Cannot update subscription with status {status_value}. Use force_update=true to override."
            )

    # Duplicate the current subscription row, excluding id and timestamps
    cls = type(current_subscription)
    exclude_fields = ["id", "created_at", "updated_at"]
    data = {
        column.name: getattr(current_subscription, column.name)
        for column in cls.__table__.columns
        if column.name not in exclude_fields
    }
    new_subscription = cls(**data)

    allowed_fields = {
        "payment_method",
        "trial_start_date",
        "start_date",
        "end_date",
        "status",
        "stripe_subscription_id",
        "subscription_plan_id",
    }

    nullable_fields = {"end_date", "trial_start_date", "stripe_subscription_id"}

    for k, v in update_data.items():
        if k in allowed_fields:
            if v is None and k not in nullable_fields:
                continue
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

    if updated_subscription is None:
        raise ValueError(f"Failed to update subscription {external_id}")

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

    subscription_to_cancel = account_subscription_repository.get_account_subscription(
        account.id, external_id
    )
    if not subscription_to_cancel:
        raise ValueError(f"Subscription with external_id {external_id} does not exist")

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

    # Cancel Stripe subscription first if it exists
    if subscription_to_cancel.stripe_subscription_id:
        stripe_cancelled = _stripe_subscription.cancel_subscription(
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

    logger.info(
        f"Cancelled subscription for account {account_name}",
        extra={
            "account_id": str(account.id),
            "subscription_external_id": str(external_id),
            "stripe_subscription_id": subscription_to_cancel.stripe_subscription_id,
        },
    )

    # Send subscription cancelled notification
    if cancelled_subscription and subscription_to_cancel.subscription_plan_id:
        subscription_plan_repository = SubscriptionPlanRepository(session)
        plan = subscription_plan_repository.get_subscription_plan_by_id(
            subscription_to_cancel.subscription_plan_id
        )
        if plan:
            _send_subscription_cancelled_notification(
                session, account, cancelled_subscription, plan
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


def get_account_subscription(
    session: Session,
    account_id: uuid.UUID,
    external_id: uuid.UUID,
) -> db.AccountSubscription | None:
    """
    Get the latest version of an account subscription by account_id and external_id.

    Args:
        session: Database session
        account_id: Account ID for authorization
        external_id: External ID of the subscription

    Returns:
        Account subscription if found, None otherwise
    """
    account_subscription_repository = AccountSubscriptionRepository(
        session, auto_commit=True
    )
    return account_subscription_repository.get_account_subscription(
        account_id, external_id
    )


def create_stripe_checkout_url(
    session: Session,
    account_id: uuid.UUID,
    external_id: uuid.UUID,
    customer_email: str | None,
    redirect_url_prefix: str,
    referral_code: str | None = None,
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
        referral_code: Optional Rewardful referral token from ?via= parameter

    Returns:
        Checkout URL string or None if subscription not found
    """
    project_subscription_repo = ProjectSubscriptionRepository(session)

    # Get subscription by external_id
    subscription = get_account_subscription_by_external_id(session, external_id)

    if not subscription or subscription.account_id != account_id:
        return None

    # Validate subscription doesn't already have a Stripe subscription ID
    # It's ok for cancelled subscriptions to have a stripe ID from previous checkouts.
    if (
        subscription.status != SubscriptionStatus.cancelled
        and subscription.stripe_subscription_id
    ):
        raise ValueError("Subscription already has a Stripe subscription ID")

    # Get project subscriptions to collect project-specific prices
    project_subscriptions = (
        project_subscription_repo.get_project_subscriptions_by_subscription_id(
            subscription.external_id
        )
    )

    if not project_subscriptions:
        raise RuntimeError(
            "No project subscriptions found for this account subscription"
        )

    # Collect all line items for the checkout session
    line_items = []
    price_details = []

    # Add project-specific usage prices
    for project_subscription in project_subscriptions:
        # Get project details for better descriptions
        project = project_service.get_project(session, project_subscription.project_id)
        project_name = (
            project.name if project else f"Project {project_subscription.project_id}"
        )
        project_display_name = (
            project.display_name if (project and project.display_name) else project_name
        )

        # Add base price
        if project_subscription.base_price_id:
            line_items.append(
                {
                    "price": project_subscription.base_price_id,
                    "quantity": 1,
                }
            )
            price_details.append(
                {
                    "project_subscription_id": str(project_subscription.id),
                    "project_id": str(project_subscription.project_id),
                    "project_name": project_name,
                    "project_display_name": project_display_name,
                    "price_type": "monthly_fee",
                    "price_id": project_subscription.base_price_id,
                    "description": f"Monthly fee for {project_display_name}",
                    "pricing_method": "existing_price_id",
                }
            )

        # Add call usage price (using existing price ID - price_data doesn't support metered billing)
        if project_subscription.call_price_id:
            line_items.append(
                {
                    "price": project_subscription.call_price_id,
                }
            )
            price_details.append(
                {
                    "project_subscription_id": str(project_subscription.id),
                    "project_id": str(project_subscription.project_id),
                    "project_name": project_name,
                    "project_display_name": project_display_name,
                    "price_type": "call_usage",
                    "price_id": project_subscription.call_price_id,
                    "description": f"Call usage for {project_display_name}",
                    "pricing_method": "existing_price_id",
                }
            )

        # Add order usage price (using existing price ID - price_data doesn't support metered billing)
        if project_subscription.order_price_id:
            line_items.append(
                {
                    "price": project_subscription.order_price_id,
                }
            )
            price_details.append(
                {
                    "project_subscription_id": str(project_subscription.id),
                    "project_id": str(project_subscription.project_id),
                    "project_name": project_name,
                    "project_display_name": project_display_name,
                    "price_type": "order_usage",
                    "price_id": project_subscription.order_price_id,
                    "description": f"Order usage for {project_display_name}",
                    "pricing_method": "existing_price_id",
                }
            )

    if not line_items:
        raise RuntimeError("No valid price IDs found for checkout session")

    # Count different price types for logging
    monthly_prices = [p for p in price_details if p["price_type"] == "monthly_plan"]
    usage_prices = [p for p in price_details if "usage" in p["price_type"]]

    # Log detailed price information for debugging
    logger.info(
        "Checkout session price breakdown",
        extra={
            "account_id": str(account_id),
            "subscription_id": str(subscription.external_id),
            "price_details": price_details,
            "total_line_items": len(line_items),
            "monthly_plan_items": len(monthly_prices),
            "usage_items": len(usage_prices),
            "projects_count": len(project_subscriptions),
        },
    )

    logger.info(
        f"Creating checkout session: {len(monthly_prices)} monthly plan + {len(usage_prices)} usage items from {len(project_subscriptions)} projects",
        extra={
            "account_id": str(account_id),
            "subscription_id": str(subscription.external_id),
            "line_items_count": len(line_items),
            "structure": "existing price IDs",
            "price_ids": [p["price_id"] for p in price_details if "price_id" in p],
        },
    )

    account = account_service.get_account_by_id(session, account_id)
    existing_stripe_customer_id = account.stripe_customer_id if account else None
    account_coupon_id = account.stripe_coupon_id if account else None

    # Create checkout session with project-specific prices
    checkout_session = _stripe_subscription.create_checkout_session(
        account_id=account_id,
        customer_email=customer_email,
        subscription_external_id=subscription.external_id,
        line_items=line_items,
        redirect_url_prefix=redirect_url_prefix,
        start_date=subscription.start_date,
        existing_customer_id=existing_stripe_customer_id,
        referral_code=referral_code,
        account_coupon_id=account_coupon_id,
    )

    if not checkout_session or not checkout_session.url:
        raise RuntimeError("Failed to create checkout session")

    return checkout_session.url


def create_stripe_checkout_url_for_project(
    session: Session,
    project_id: uuid.UUID,
    external_id: uuid.UUID,
    customer_email: str | None,
    redirect_url_prefix: str,
    referral_code: str | None = None,
) -> str | None:
    """
    Create a Stripe checkout URL for an independent project subscription.

    This function creates a checkout session for project subscriptions that have
    their own Stripe billing (subscription_id == external_id).

    Args:
        session: Database session
        project_id: UUID of the project
        external_id: External ID of the project subscription
        customer_email: Optional email for the customer
        redirect_url_prefix: URL prefix for success/cancel redirects
        referral_code: Optional Rewardful referral token from ?via= parameter

    Returns:
        Checkout URL string or None if subscription not found

    Raises:
        ValueError: If subscription already has Stripe ID or is account-linked
        RuntimeError: If no valid prices found
    """
    project_subscription_repo = ProjectSubscriptionRepository(session)

    # Get project subscription by external_id
    project_subscription = (
        project_subscription_repo.get_project_subscription_by_external_id(external_id)
    )

    if not project_subscription or project_subscription.project_id != project_id:
        return None

    # Validate this is an independent project subscription
    if project_subscription.subscription_id != project_subscription.external_id:
        raise ValueError(
            "Cannot create checkout for account-linked project subscription. "
            "Use account-level checkout instead."
        )

    # Validate subscription doesn't already have a Stripe subscription ID
    # It's ok for cancelled subscriptions to have a stripe ID from previous checkouts
    if (
        project_subscription.status != SubscriptionStatus.cancelled
        and project_subscription.stripe_subscription_id
    ):
        raise ValueError("Subscription already has a Stripe subscription ID")

    # Get project details for better descriptions
    project = project_service.get_project(session, project_id)
    if not project:
        raise ValueError(f"Project {project_id} not found")

    project_name = project.name
    project_display_name = (
        project.display_name if project.display_name else project_name
    )

    # Collect all line items for the checkout session
    line_items = []
    price_details = []

    # Add base price (monthly fee)
    if project_subscription.base_price_id:
        line_items.append(
            {
                "price": project_subscription.base_price_id,
                "quantity": 1,
            }
        )
        price_details.append(
            {
                "project_subscription_id": str(project_subscription.id),
                "project_id": str(project_id),
                "project_name": project_name,
                "project_display_name": project_display_name,
                "price_type": "monthly_fee",
                "price_id": project_subscription.base_price_id,
                "description": f"Monthly fee for {project_display_name}",
            }
        )

    # Add call usage price (metered billing)
    if project_subscription.call_price_id:
        line_items.append(
            {
                "price": project_subscription.call_price_id,
            }
        )
        price_details.append(
            {
                "project_subscription_id": str(project_subscription.id),
                "project_id": str(project_id),
                "project_name": project_name,
                "project_display_name": project_display_name,
                "price_type": "call_usage",
                "price_id": project_subscription.call_price_id,
                "description": f"Call usage for {project_display_name}",
            }
        )

    # Add order usage price (metered billing)
    if project_subscription.order_price_id:
        line_items.append(
            {
                "price": project_subscription.order_price_id,
            }
        )
        price_details.append(
            {
                "project_subscription_id": str(project_subscription.id),
                "project_id": str(project_id),
                "project_name": project_name,
                "project_display_name": project_display_name,
                "price_type": "order_usage",
                "price_id": project_subscription.order_price_id,
                "description": f"Order usage for {project_display_name}",
            }
        )

    if not line_items:
        raise RuntimeError("No valid price IDs found for checkout session")

    logger.info(
        "Creating project checkout session",
        extra={
            "project_id": str(project_id),
            "subscription_external_id": str(external_id),
            "price_details": price_details,
            "line_items_count": len(line_items),
        },
    )

    # Get account for customer information
    account = account_service.get_account_by_id(session, project.account_id)
    if not account:
        raise ValueError(f"Account {project.account_id} not found")

    existing_stripe_customer_id = account.stripe_customer_id
    account_coupon_id = account.stripe_coupon_id

    # Create checkout session with project-specific prices
    checkout_session = _stripe_subscription.create_checkout_session(
        account_id=project.account_id,
        customer_email=customer_email,
        subscription_external_id=external_id,
        line_items=line_items,
        redirect_url_prefix=redirect_url_prefix,
        start_date=project_subscription.start_date,
        existing_customer_id=existing_stripe_customer_id,
        referral_code=referral_code,
        account_coupon_id=account_coupon_id,
        subscription_type="project",
        project_id=project_id,
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
    project: db.Project,
    subscription_id: uuid.UUID,
) -> db.ProjectSubscription:
    """
    Create a new project subscription.

    Args:
        session: Database session
        project: The project to add to subscription
        subscription_id: ID of the subscription

    Returns:
        The created project subscription record
    """
    project_subscription_repository = ProjectSubscriptionRepository(
        session, auto_commit=False
    )

    # Validate subscription exists
    subscription = get_account_subscription_by_external_id(session, subscription_id)
    if not subscription:
        raise ValueError(f"Subscription {subscription_id} does not exist")

    # Check if project subscription already exists
    existing_project_subscription = (
        project_subscription_repository.get_project_subscription(
            project.id, subscription_id
        )
    )
    if existing_project_subscription:
        raise ValueError(
            f"Project subscription already exists for project {project.id} and subscription {subscription_id}"
        )

    project_subscription = add_project_to_subscription(session, subscription, project)

    try:
        session.commit()
    except Exception as err:
        session.rollback()
        logger.error(f"Failed to commit db change due to error: {err}")
        raise err

    return project_subscription


def remove_project_subscription(
    session: Session,
    project_id: uuid.UUID,
    subscription_id: uuid.UUID,
    remove_subscription_item=True,
):
    """
    Remove a project subscription (soft delete).

    This operation is idempotent - if the project subscription does not exist,
    it will return gracefully without raising an error.

    Args:
        session: Database session
        project_id: Project ID to be removed
        subscription_id: ID of the subscription
        remove_subscription_item: whether to actively remove the line item from stripe subscription
    """
    project_subscription_repository = ProjectSubscriptionRepository(
        session, auto_commit=False
    )

    # Check if project subscription exists
    project_subscription = project_subscription_repository.get_project_subscription(
        project_id, subscription_id
    )
    if not project_subscription:
        # Return gracefully if already removed (idempotent operation)
        logger.info(
            f"Project subscription already removed or does not exist for project {project_id} and subscription {subscription_id}"
        )
        return

    # Get subscription details for Stripe update
    subscription = get_account_subscription_by_external_id(session, subscription_id)
    if not subscription:
        raise ValueError(f"Subscription {subscription_id} does not exist")

    # Step 1: Delete subscription items associated with the prices if available
    if remove_subscription_item and subscription.stripe_subscription_id:
        if project_subscription.call_price_id:
            _stripe_subscription.remove_subscription_item(
                subscription.stripe_subscription_id,
                project_subscription.call_price_id,
            )
        if project_subscription.order_price_id:
            _stripe_subscription.remove_subscription_item(
                subscription.stripe_subscription_id,
                project_subscription.order_price_id,
            )

    # Step 2: Soft delete the project subscription record
    project_subscription_repository.delete_project_subscription(
        project_id, subscription_id
    )

    logger.info(
        "Successfully removed project from subscription!",
        extra={
            "project_id": project_id,
            "account_subscription_id": subscription.external_id,
        },
    )


def get_stripe_customer_id_for_project(
    session: Session, project_id: uuid.UUID
) -> str | None:
    """
    Get the Stripe customer ID associated with a project's account.

    Args:
        session: Database session
        project_id: Project ID to get customer ID for

    Returns:
        str | None: Stripe customer ID if found, None otherwise
    """
    try:
        project_repo = db.ProjectRepository(session)
        project = project_repo.get_project(project_id)

        if not project:
            logger.warning(
                f"Project {project_id} not found when getting Stripe customer ID",
                extra={"project_id": str(project_id)},
            )
            return None

        account_repo = db.AccountRepository(session)
        account = account_repo.get_account_by_id(project.account_id)

        if not account:
            logger.warning(
                f"Account {project.account_id} not found when getting Stripe customer ID",
                extra={
                    "project_id": str(project_id),
                    "account_id": str(project.account_id),
                },
            )
            return None

        if not account.stripe_customer_id:
            return None

        return account.stripe_customer_id

    except Exception as e:
        logger.error(
            f"Error getting Stripe customer ID for project {project_id}: {e}",
            extra={
                "project_id": str(project_id),
            },
            exc_info=True,
        )
        return None


def grant_credit_to_account(
    account: db.Account,
    credit_amount_cents: int,
    currency: str,
    description: str | None,
    issued_by: str | None = None,
    metadata: dict[str, str] | None = None,
    idempotency_key: str | None = None,
):
    if not account.stripe_customer_id:
        raise ValueError(
            "Account does not have a stripe customer associated, does it have a subscription?"
        )

    audit_metadata = metadata.copy() if metadata else {}

    if issued_by:
        audit_metadata["issued_by"] = issued_by

    audit_metadata.update(
        {
            "account_name": account.name,
            "account_id": str(account.id),
            "credit_amount_dollars": f"{(D(credit_amount_cents) / D('100')).quantize(D('0.01'))}",
            "issued_at": datetime.now(UTC).isoformat(),
        }
    )

    return _stripe_customer.grant_credit_balance(
        account.stripe_customer_id,
        credit_amount_cents,
        currency,
        description,
        audit_metadata,
        idempotency_key,
    )


def get_account_credit_balance(
    account: db.Account,
) -> tuple[int, str]:

    if not account.stripe_customer_id:
        raise ValueError(
            "Account does not have a stripe customer associated, does it have a subscription?"
        )

    return _stripe_customer.get_credit_balance(account.stripe_customer_id)


def get_account_credit_grants(
    account: db.Account,
) -> list[dict]:
    if not account.stripe_customer_id:
        raise ValueError(
            "Account does not have a stripe customer associated, does it have a subscription?"
        )

    return _stripe_customer.get_credit_grants_history(
        account.stripe_customer_id,
    )


def switch_subscription_plan(
    session: Session,
    context: UserContext,
    account: db.Account,
    new_plan_id: uuid.UUID,
    prorate: bool = False,
) -> tuple[db.AccountSubscription, str, str]:
    if not account.current_subscription_id:
        raise ValueError("Account has no active subscription to switch")

    current_subscription = get_current_subscription(session, account)
    if not current_subscription:
        raise ValueError("Current subscription not found")

    if current_subscription.status != SubscriptionStatus.active:
        raise ValueError("Can only switch plans for active subscriptions")

    subscription_plan_repository = SubscriptionPlanRepository(session)
    current_plan = subscription_plan_repository.get_subscription_plan_by_id(
        current_subscription.subscription_plan_id
    )
    new_plan = subscription_plan_repository.get_subscription_plan_by_id(new_plan_id)

    if not current_plan:
        raise ValueError("Current subscription plan not found")
    if not new_plan:
        raise ValueError(f"New subscription plan '{new_plan_id}' not found")
    if not new_plan.active:
        raise ValueError("Cannot switch to inactive plan")

    if current_plan.id == new_plan.id:
        raise ValueError("Cannot switch to the same plan")

    project_subscription_repository = ProjectSubscriptionRepository(session)
    project_subscriptions = (
        project_subscription_repository.get_project_subscriptions_by_subscription_id(
            current_subscription.external_id
        )
    )

    if not project_subscriptions:
        raise ValueError("No project subscriptions found for current subscription")

    if current_subscription.stripe_subscription_id:
        _update_stripe_subscription_for_plan_switch(
            session,
            current_subscription,
            project_subscriptions,
            new_plan,
            account.name,
            prorate,
        )

        try:
            session.commit()
        except Exception as err:
            session.rollback()
            logger.error(
                "Failed to commit project subscription updates after Stripe changes",
                extra={
                    "account_id": str(account.id),
                    "subscription_external_id": str(current_subscription.external_id),
                    "old_plan_id": str(current_plan.id),
                    "new_plan_id": str(new_plan.id),
                    "projects_updated": len(project_subscriptions),
                },
                exc_info=True,
            )
            raise err
    else:
        logger.warning(
            "No Stripe subscription ID found, skipping Stripe updates",
            extra={
                "account_id": str(account.id),
                "subscription_id": str(current_subscription.external_id),
            },
        )

    new_subscription_data = {
        "subscription_plan_id": new_plan.id,
    }

    new_subscription = update_account_subscription(
        session=session,
        context=context,
        account_id=account.id,
        external_id=current_subscription.external_id,
        update_data=new_subscription_data,
    )

    logger.info(
        "Successfully switched subscription plan",
        extra={
            "account_id": str(account.id),
            "account_name": account.name,
            "subscription_id": str(current_subscription.external_id),
            "old_plan_id": str(current_plan.id),
            "old_plan_name": current_plan.name,
            "new_plan_id": str(new_plan.id),
            "new_plan_name": new_plan.name,
            "prorated": prorate,
        },
    )

    return new_subscription, current_plan.name, new_plan.name


def switch_project_subscription_plan(
    session: Session,
    context: UserContext,
    project_id: uuid.UUID,
    new_plan_id: uuid.UUID,
    prorate: bool = False,
) -> tuple[db.ProjectSubscription, str, str]:
    """
    Switch an independent project subscription to a different plan.

    IMPORTANT: This function only works for independent project subscriptions
    (where subscription_id == external_id). For project subscriptions linked to
    an account-level subscription, use switch_subscription_plan() instead, which
    will update all linked project subscriptions together.

    This function:
    1. Validates the project has an active, independent subscription
    2. Guards against account-linked subscriptions and missing Stripe IDs
    3. Creates new Stripe product/prices for the new plan
    4. Updates Stripe subscription items (with optional proration)
    5. Updates the database with the new plan and price IDs

    Args:
        session: Database session
        context: User context for authorization
        project_id: Project UUID
        new_plan_id: Target subscription plan UUID
        prorate: Whether to prorate the charges (default: True)

    Returns:
        Tuple of (updated_subscription, old_plan_name, new_plan_name)

    Raises:
        ValueError: If subscription not found, not active, is account-linked,
                   missing Stripe ID, or plan invalid
    """
    project_subscription_repository = ProjectSubscriptionRepository(session)
    active_project_sub = (
        project_subscription_repository.get_active_project_subscription(project_id)
    )

    if not active_project_sub:
        raise ValueError("Project has no active subscription to switch")

    if active_project_sub.status != SubscriptionStatus.active:
        raise ValueError("Can only switch plans for active subscriptions")

    # Guard against switching account-linked project subscriptions
    # If subscription_id != external_id, this project subscription is linked to
    # an account-level subscription and should use account-level switch flow
    if active_project_sub.subscription_id != active_project_sub.external_id:
        raise ValueError(
            "Cannot switch plan for account-linked project subscription. "
            "Use account-level plan switching instead, which will update all "
            "project subscriptions linked to the account subscription."
        )

    # Independent project subscriptions must have their own Stripe subscription
    if not active_project_sub.stripe_subscription_id:
        raise ValueError(
            "Project subscription has no Stripe subscription ID. "
            "Cannot switch plan without Stripe synchronization."
        )

    subscription_plan_repository = SubscriptionPlanRepository(session)

    if not active_project_sub.subscription_plan_id:
        raise ValueError("Project subscription has no plan ID")

    current_plan = subscription_plan_repository.get_subscription_plan_by_id(
        active_project_sub.subscription_plan_id
    )
    new_plan = subscription_plan_repository.get_subscription_plan_by_id(new_plan_id)

    if not current_plan:
        raise ValueError("Current subscription plan not found")
    if not new_plan:
        raise ValueError(f"New subscription plan '{new_plan_id}' not found")
    if not new_plan.active:
        raise ValueError("Cannot switch to inactive plan")

    if current_plan.id == new_plan.id:
        raise ValueError("Cannot switch to the same plan")

    # Get project and account for Stripe operations
    project = project_service.get_project(session, project_id)
    if not project:
        raise ValueError(f"Project {project_id} not found")

    account = account_service.get_account_by_id(session, project.account_id)
    if not account:
        raise ValueError(f"Account {project.account_id} not found")

    # Update Stripe subscription items with new prices
    # Note: We already validated stripe_subscription_id exists in guard above
    _update_stripe_subscription_for_project_plan_switch(
        session,
        active_project_sub,
        new_plan,
        project,
        account.name,
        prorate,
    )

    try:
        session.commit()
    except Exception as err:
        session.rollback()
        logger.error(
            "Failed to commit project subscription updates after Stripe changes",
            extra={
                "project_id": str(project_id),
                "subscription_external_id": str(active_project_sub.external_id),
                "old_plan_id": str(current_plan.id),
                "new_plan_id": str(new_plan.id),
            },
            exc_info=True,
        )
        raise err

    # Update database with new plan
    if not active_project_sub.external_id:
        raise ValueError("Project subscription has no external ID")

    new_subscription_data = {
        "subscription_plan_id": new_plan.id,
    }

    new_subscription = update_project_subscription(
        session=session,
        context=context,
        project_id=project_id,
        external_id=active_project_sub.external_id,
        update_data=new_subscription_data,
    )

    logger.info(
        "Successfully switched project subscription plan",
        extra={
            "project_id": str(project_id),
            "subscription_id": str(active_project_sub.external_id),
            "old_plan_id": str(current_plan.id),
            "old_plan_name": current_plan.name,
            "new_plan_id": str(new_plan.id),
            "new_plan_name": new_plan.name,
            "prorated": prorate,
        },
    )

    return new_subscription, current_plan.name, new_plan.name


def _update_stripe_subscription_for_project_plan_switch(
    session: Session,
    project_subscription: db.ProjectSubscription,
    new_plan: db.SubscriptionPlan,
    project: db.Project,
    account_name: str,
    prorate: bool,
) -> None:
    """
    Update Stripe subscription items for a single project's plan switch.

    Creates new products/prices for the new plan and updates the subscription
    items, removing old ones and adding new ones. Proration behavior is controlled
    by the prorate parameter.
    """
    if not project_subscription.stripe_subscription_id:
        raise ValueError(
            "Project subscription must have Stripe subscription ID to update"
        )

    stripe_subscription_id = project_subscription.stripe_subscription_id
    proration_behavior = "create_prorations" if prorate else "none"

    project_name = project.name
    project_display_name = (
        project.display_name if project.display_name else project_name
    )

    # Create new Stripe product for the new plan
    new_product_id = _stripe_product.create_product_for_project(
        project, account_name, new_plan.name
    )

    # Store old price IDs for in-place swapping
    old_base_price_id = project_subscription.base_price_id
    old_call_price_id = project_subscription.call_price_id
    old_order_price_id = project_subscription.order_price_id

    # Create base price (monthly fee) if applicable
    new_base_price_id = None
    if new_plan.monthly_fee and new_plan.monthly_fee > 0:
        new_base_price_id = _stripe_product.create_product_price(
            new_product_id,
            nickname=f"Flat fee - {project_display_name}",
            project=project,
            flat_fee=new_plan.monthly_fee,
        )

    # Setup call pricing for new plan
    call_meter_id = _stripe_product.create_billing_meter(
        f"{project_name} calls",
        _stripe_product.get_call_meter_event_name(project.id),
    )
    new_call_price_id = _stripe_product.create_product_price(
        new_product_id,
        nickname=f"Calls - {project_display_name}",
        project=project,
        meter_tiers=_build_call_tiers(new_plan),
        meter_id=call_meter_id,
    )

    # Setup order pricing for new plan if applicable
    new_order_price_id = None
    if new_plan.order_overage_charge and new_plan.order_overage_charge > 0:
        order_meter_id = _stripe_product.create_billing_meter(
            f"{project_name} orders",
            _stripe_product.get_order_meter_event_name(project.id),
        )
        new_order_price_id = _stripe_product.create_product_price(
            new_product_id,
            nickname=f"Orders - {project_display_name}",
            meter_tiers=_build_order_tiers(new_plan),
            project=project,
            meter_id=order_meter_id,
        )

    # Update base price (monthly fee)
    if old_base_price_id and new_base_price_id:
        _stripe_subscription.update_subscription_item_price(
            stripe_subscription_id,
            old_base_price_id,
            new_base_price_id,
            proration_behavior=proration_behavior,
        )
    elif old_base_price_id and not new_base_price_id:
        _stripe_subscription.remove_subscription_item(
            stripe_subscription_id,
            old_base_price_id,
            proration_behavior=proration_behavior,
        )
    elif new_base_price_id and not old_base_price_id:
        _stripe_subscription.add_subscription_item(
            stripe_subscription_id,
            new_base_price_id,
            proration_behavior=proration_behavior,
        )

    # Update call pricing (metered)
    if old_call_price_id and new_call_price_id:
        _stripe_subscription.update_subscription_item_price(
            stripe_subscription_id,
            old_call_price_id,
            new_call_price_id,
            proration_behavior=proration_behavior,
        )
    elif old_call_price_id and not new_call_price_id:
        _stripe_subscription.remove_subscription_item(
            stripe_subscription_id,
            old_call_price_id,
            proration_behavior=proration_behavior,
        )
    elif new_call_price_id and not old_call_price_id:
        _stripe_subscription.add_subscription_item(
            stripe_subscription_id,
            new_call_price_id,
            proration_behavior=proration_behavior,
        )

    # Update order pricing (metered)
    if old_order_price_id and new_order_price_id:
        _stripe_subscription.update_subscription_item_price(
            stripe_subscription_id,
            old_order_price_id,
            new_order_price_id,
            proration_behavior=proration_behavior,
        )
    elif old_order_price_id and not new_order_price_id:
        _stripe_subscription.remove_subscription_item(
            stripe_subscription_id,
            old_order_price_id,
            proration_behavior=proration_behavior,
        )
    elif new_order_price_id and not old_order_price_id:
        _stripe_subscription.add_subscription_item(
            stripe_subscription_id,
            new_order_price_id,
            proration_behavior=proration_behavior,
        )

    # Update project subscription record with new Stripe-related fields only
    # Note: subscription_plan_id is updated separately by the main function
    # via update_project_subscription which creates a versioned record
    project_subscription_repository = ProjectSubscriptionRepository(
        session, auto_commit=False
    )
    project_subscription_repository.update_project_subscription(
        project_subscription.id,
        stripe_product_id=new_product_id,
        base_price_id=new_base_price_id,
        call_price_id=new_call_price_id,
        order_price_id=new_order_price_id,
    )

    logger.info(
        f"Updated Stripe subscription items for project {project.id}",
        extra={
            "project_id": str(project.id),
            "stripe_subscription_id": stripe_subscription_id,
            "new_product_id": new_product_id,
            "base_price_id": new_base_price_id,
            "call_price_id": new_call_price_id,
            "order_price_id": new_order_price_id,
        },
    )


def _update_stripe_subscription_for_plan_switch(
    session: Session,
    current_subscription: db.AccountSubscription,
    project_subscriptions: list[db.ProjectSubscription],
    new_plan: db.SubscriptionPlan,
    account_name: str,
    prorate: bool,
) -> None:
    """
    Update Stripe subscription items for plan switching.

    This creates new products/prices for the new plan and updates the subscription
    items, removing old ones and adding new ones. Proration behavior is controlled
    by the prorate parameter.
    """
    if not current_subscription.stripe_subscription_id:
        raise ValueError("Subscription must have Stripe subscription ID to update")

    stripe_subscription_id = current_subscription.stripe_subscription_id
    proration_behavior = "create_prorations" if prorate else "none"

    for project_subscription in project_subscriptions:
        project = project_service.get_project(session, project_subscription.project_id)
        if not project:
            logger.warning(
                f"Project {project_subscription.project_id} not found, skipping"
            )
            continue

        project_name = project.name
        project_display_name = (
            project.display_name if project.display_name else project_name
        )

        new_product_id = _stripe_product.create_product_for_project(
            project, account_name, new_plan.name
        )

        # Store old price IDs for in-place swapping
        old_base_price_id = project_subscription.base_price_id
        old_call_price_id = project_subscription.call_price_id
        old_order_price_id = project_subscription.order_price_id

        new_base_price_id = None
        if new_plan.monthly_fee and new_plan.monthly_fee > 0:
            new_base_price_id = _stripe_product.create_product_price(
                new_product_id,
                nickname=f"Flat fee - {project_display_name}",
                project=project,
                flat_fee=new_plan.monthly_fee,
            )

        # Setup call pricing for new plan
        call_meter_id = _stripe_product.create_billing_meter(
            f"{project_name} calls",
            _stripe_product.get_call_meter_event_name(project.id),
        )
        new_call_price_id = _stripe_product.create_product_price(
            new_product_id,
            nickname=f"Calls - {project_display_name}",
            project=project,
            meter_tiers=_build_call_tiers(new_plan),
            meter_id=call_meter_id,
        )

        # Setup order pricing for new plan if applicable
        new_order_price_id = None
        if new_plan.order_overage_charge and new_plan.order_overage_charge > 0:
            order_meter_id = _stripe_product.create_billing_meter(
                f"{project_name} orders",
                _stripe_product.get_order_meter_event_name(project.id),
            )
            new_order_price_id = _stripe_product.create_product_price(
                new_product_id,
                nickname=f"Orders - {project_display_name}",
                meter_tiers=_build_order_tiers(new_plan),
                project=project,
                meter_id=order_meter_id,
            )

        # Swap in-place to avoid dual metering; add/remove only when structure changes
        if old_base_price_id and new_base_price_id:
            _stripe_subscription.update_subscription_item_price(
                stripe_subscription_id,
                old_base_price_id,
                new_base_price_id,
                proration_behavior=proration_behavior,
            )
        elif old_base_price_id and not new_base_price_id:
            _stripe_subscription.remove_subscription_item(
                stripe_subscription_id,
                old_base_price_id,
                proration_behavior=proration_behavior,
            )
        elif new_base_price_id and not old_base_price_id:
            _stripe_subscription.add_subscription_item(
                stripe_subscription_id,
                new_base_price_id,
                proration_behavior=proration_behavior,
            )

        # Calls (metered)
        if old_call_price_id and new_call_price_id:
            _stripe_subscription.update_subscription_item_price(
                stripe_subscription_id,
                old_call_price_id,
                new_call_price_id,
                proration_behavior=proration_behavior,
            )
        elif old_call_price_id and not new_call_price_id:
            _stripe_subscription.remove_subscription_item(
                stripe_subscription_id,
                old_call_price_id,
                proration_behavior=proration_behavior,
            )
        elif new_call_price_id and not old_call_price_id:
            _stripe_subscription.add_subscription_item(
                stripe_subscription_id,
                new_call_price_id,
                proration_behavior=proration_behavior,
            )

        # Orders (metered)
        if old_order_price_id and new_order_price_id:
            _stripe_subscription.update_subscription_item_price(
                stripe_subscription_id,
                old_order_price_id,
                new_order_price_id,
                proration_behavior=proration_behavior,
            )
        elif old_order_price_id and not new_order_price_id:
            _stripe_subscription.remove_subscription_item(
                stripe_subscription_id,
                old_order_price_id,
                proration_behavior=proration_behavior,
            )
        elif new_order_price_id and not old_order_price_id:
            _stripe_subscription.add_subscription_item(
                stripe_subscription_id,
                new_order_price_id,
                proration_behavior=proration_behavior,
            )

        # Update project subscription record with all new price IDs in single DB write
        project_subscription_repository = ProjectSubscriptionRepository(
            session, auto_commit=False
        )
        project_subscription_repository.update_project_subscription(
            id=project_subscription.id,
            stripe_product_id=new_product_id,
            base_price_id=new_base_price_id,  # clear to None when no monthly fee
            call_price_id=new_call_price_id,
            order_price_id=new_order_price_id,
        )

        logger.info(
            "Updated Stripe subscription items for project",
            extra={
                "project_id": str(project.id),
                "project_name": project_name,
                "old_product_id": project_subscription.stripe_product_id,
                "new_product_id": new_product_id,
                "prorated": prorate,
            },
        )


async def should_block_calls_async(session: AsyncSession, account: db.Account) -> bool:
    if account.current_subscription_id:
        current_subscription = await get_current_subscription_async(session, account)
        # if subscription status is invalid, block right away
        if current_subscription and current_subscription.status in [
            SubscriptionStatus.cancelled,
            SubscriptionStatus.expired,
            SubscriptionStatus.deleted,
        ]:
            return True
        # if subscription status is valid, the call should not be blocked
        elif current_subscription and current_subscription.status in [
            SubscriptionStatus.active,
        ]:
            return False
    # at this point, we don't have a confirmed subscription status
    if account.onboarding_method == OnboardingMethod.self_onboarding:
        # for self onboarded accounts, only block if their call count exceeds 100
        # this parameter will be moved to the accounts table in the future so we
        # configure it dynamically.
        conversation_repository = ConversationRepositoryAsync(session)
        call_count = await conversation_repository.count_conversations_by_account_id(
            account.id
        )
        return call_count > 100
    else:
        # for all other accounts, do not block
        return False


def unlink_subscription_from_account(
    session: Session,
    context: UserContext,
    account: db.Account,
    force_unlink: bool = False,
) -> None:
    """
    Unlink a subscription from an account by setting current_subscription_id to null.
    Only allows unlinking if the subscription status is not active or pending.
    """
    account_subscription_repo = AccountSubscriptionRepository(session)

    external_id = account.current_subscription_id
    if not external_id:
        return

    subscription = account_subscription_repo.get_account_subscription(
        account.id, external_id
    )

    if not subscription:
        error_msg = (
            f"The subscription linked to the account is not found: {external_id}"
        )
        logger.error(error_msg)
        if not force_unlink:
            raise ValueError(error_msg)
    elif subscription.status in [SubscriptionStatus.active, SubscriptionStatus.pending]:
        if force_unlink:
            logger.warning(
                "Subscription has invalid status, but we are forcing the unlink anyway.",
                extra={
                    "account_name": account.name,
                    "current_subscription_status": subscription.status,
                },
            )
        else:
            raise ValueError(
                f"Cannot unlink subscription with status '{subscription.status}'. "
                "Only cancelled, expired, or deleted subscriptions can be unlinked."
            )

    with change_log_context(
        session=session,
        resource_type=ChangeResourceType.Account,
        author=context.email,
        account_id=account.id,
        resource_id=str(account.id),
        auto_commit=False,
    ):
        account.current_subscription_id = None
        session.commit()

        logger.info(
            "Successfully unlinked subscription from account",
            extra={
                "account_name": str(account.name),
                "subscription_external_id": str(external_id),
            },
        )


def create_stripe_customer_for_account(
    session: Session,
    context: UserContext,
    account: db.Account,
    customer_name: str | None = None,
    customer_email: str | None = None,
) -> CustomerInfo:
    """
    Create a Stripe customer for an account and update the account record.
    """
    if account.stripe_customer_id:
        raise ValueError(
            f"Account {account.name} already has a Stripe customer: {account.stripe_customer_id}"
        )

    try:
        customer_info = _stripe_customer.create_stripe_customer(
            account_name=account.name,
            customer_name=customer_name,
            customer_email=customer_email,
            metadata={
                "account_id": str(account.id),
                "created_via": "admin_api",
            },
        )

        with change_log_context(
            session=session,
            resource_type=ChangeResourceType.Account,
            author=context.email,
            account_id=account.id,
            resource_id=str(account.id),
            auto_commit=False,
        ):
            account.stripe_customer_id = customer_info.id
            session.commit()

        logger.info(
            "Successfully created and linked Stripe customer to account",
            extra={
                "account_id": str(account.id),
                "account_name": account.name,
                "customer_id": customer_info.id,
            },
        )
        return customer_info
    except Exception as e:
        session.rollback()
        logger.error(
            f"Failed to create Stripe customer for account: {e}",
            extra={
                "account_id": str(account.id),
                "account_name": account.name,
                "error": str(e),
            },
        )
        raise


def create_stripe_customer_for_project(
    session: Session,
    context: UserContext,
    project: db.Project,
    account: db.Account,
    customer_name: str | None = None,
    customer_email: str | None = None,
) -> CustomerInfo:
    """
    Create a Stripe customer for a project and update the project record.

    This is used for independent project subscriptions where the project has its own
    Stripe customer hierarchy separate from the account.
    """
    if project.stripe_customer_id:
        raise ValueError(
            f"Project {project.name} already has a Stripe customer: {project.stripe_customer_id}"
        )

    try:
        # Create consistent customer name: accountname-projectname
        # Avoid duplication if project name already starts with account name
        project_name_lower = project.name.lower()
        account_name_lower = account.name.lower()

        if project_name_lower.startswith(f"{account_name_lower}-"):
            # Project name already includes account name, use as-is
            combined_name = project_name_lower
        else:
            # Combine account and project names
            combined_name = f"{account_name_lower}-{project_name_lower}"

        customer_info = _stripe_customer.create_stripe_customer(
            account_name=combined_name,
            customer_name=customer_name or combined_name,
            customer_email=customer_email,
            metadata={
                "project_id": str(project.id),
                "project_name": project.name,
                "account_id": str(account.id),
                "account_name": account.name,
                "created_via": "admin_api",
            },
        )

        with change_log_context(
            session=session,
            resource_type=ChangeResourceType.Project,
            author=context.email,
            account_id=account.id,
            resource_id=str(project.id),
            auto_commit=False,
        ):
            project.stripe_customer_id = customer_info.id
            session.commit()

        logger.info(
            "Successfully created and linked Stripe customer to project",
            extra={
                "project_id": str(project.id),
                "project_name": project.name,
                "account_id": str(account.id),
                "account_name": account.name,
                "customer_id": customer_info.id,
            },
        )
        return customer_info
    except Exception as e:
        session.rollback()
        logger.error(
            f"Failed to create Stripe customer for project: {e}",
            extra={
                "project_id": str(project.id),
                "project_name": project.name,
                "account_id": str(account.id),
                "account_name": account.name,
                "error": str(e),
            },
        )
        raise


def get_stripe_customer_info_for_account(
    account: db.Account,
) -> CustomerInfo | None:
    """
    Get Stripe customer information for an account.
    """
    if not account.stripe_customer_id:
        return None

    try:
        return _stripe_customer.get_stripe_customer_info(account.stripe_customer_id)
    except Exception as e:
        logger.error(
            f"Failed to retrieve Stripe customer info for account: {e}",
            extra={
                "account_id": str(account.id),
                "account_name": account.name,
                "stripe_customer_id": account.stripe_customer_id,
                "error": str(e),
            },
        )
        raise


def update_stripe_customer_for_account(
    account: db.Account,
    name: str | None = None,
    email: str | None = None,
) -> CustomerInfo | None:
    """
    Update Stripe customer information for an account.
    """
    if not account.stripe_customer_id:
        return None

    try:
        return _stripe_customer.update_stripe_customer(
            stripe_customer_id=account.stripe_customer_id,
            name=name,
            email=email,
        )
    except Exception as e:
        logger.error(
            f"Failed to update Stripe customer info for account: {e}",
            extra={
                "account_id": str(account.id),
                "account_name": account.name,
                "stripe_customer_id": account.stripe_customer_id,
                "error": str(e),
            },
        )
        raise


def get_subscription_details(session: Session, account: db.Account) -> dict:
    """
    Get comprehensive subscription and billing details for an account.

    Fetches:
    - Current subscription info
    - Usage metrics (calls used, overage)
    - Recent invoices
    - Payment method info
    - Billing cycle details
    - Upgrade/downgrade options

    Args:
        session: Database session
        account: Account to fetch details for

    Returns:
        Dictionary with all billing and subscription details
    """
    from services.subscription_service._billing_details import (
        TIER_ORDER,
        get_billing_cycle_info,
        get_payment_method_info,
        get_recent_invoices,
        get_upgrade_options,
        get_usage_metrics,
    )

    # Get current subscription
    subscription = get_current_subscription(session, account)

    # Determine current plan
    plan_name = None
    current_plan_id = None
    current_tier = None
    current_plan_tier_value = 0
    plan_features = []

    if subscription and subscription.subscription_plan:
        plan_name = subscription.subscription_plan.name
        current_plan_id = str(subscription.subscription_plan.id)
        current_tier = subscription.subscription_plan.tier
        current_plan_tier_value = TIER_ORDER.get(current_tier, 0)
        # Use features_included from the subscription plan
        plan_features = subscription.subscription_plan.features_included or []

    # Get Stripe data
    stripe_customer_id = account.stripe_customer_id
    stripe_subscription_id = (
        subscription.stripe_subscription_id if subscription else None
    )

    # Fetch usage metrics
    usage = get_usage_metrics(session, account, subscription, stripe_customer_id)

    # Fetch invoices
    invoices = get_recent_invoices(stripe_customer_id, limit=10)

    # Get payment method info
    payment_status, last4, brand = get_payment_method_info(stripe_customer_id)

    # Get billing cycle info
    billing_cycle, next_billing_date, current_period_start, current_period_end = (
        get_billing_cycle_info(stripe_subscription_id)
    )

    # Get upgrade options from database
    upgrade_options = get_upgrade_options(session, current_plan_id, current_tier)

    logger.info(
        f"Fetched comprehensive subscription details for account {account.name}",
        extra={
            "account_id": str(account.id),
            "plan_name": plan_name,
            "has_invoices": len(invoices) > 0,
        },
    )

    return {
        "subscription": subscription,
        "plan_name": plan_name,
        "plan_features": plan_features,
        "billing_cycle": billing_cycle,
        "next_billing_date": next_billing_date,
        "current_period_start": current_period_start,
        "current_period_end": current_period_end,
        "usage": usage,
        "payment_status": payment_status,
        "payment_method_last4": last4,
        "payment_method_brand": brand,
        "recent_invoices": invoices,
        "upgrade_options": upgrade_options,
        "current_plan_tier": current_plan_tier_value,
    }


# ============================================================================
# Project Subscription Management Functions
# ============================================================================


def create_independent_project_subscription(
    session: Session,
    context: UserContext,
    project_id: uuid.UUID,
    subscription_params: SubscriptionParams,
) -> db.ProjectSubscription:
    """
    Create an independent project-level subscription with Stripe integration.

    This creates a subscription at the project level, separate from any account-level
    subscription. The project subscription has its own Stripe product, pricing, and billing.

    This differs from create_project_subscription() which links a project to an existing
    account subscription. This function creates a standalone project subscription.

    Args:
        session: Database session
        context: User context for authorization and logging
        project_id: Project ID to create subscription for
        subscription_params: Subscription parameters (plan_id, start_date, etc.)

    Returns:
        Created ProjectSubscription instance

    Raises:
        ValueError: If validation fails or project doesn't exist
        RuntimeError: If Stripe integration fails
    """
    # Get the project
    project = project_service.get_project(session, project_id)
    if not project:
        raise ValueError(f"Project {project_id} does not exist")

    # Get the account for Stripe customer
    account = account_service.get_account_by_id(session, project.account_id)
    if not account:
        raise ValueError(f"Account {project.account_id} does not exist")

    # Validate the subscription plan
    subscription_plan_repository = SubscriptionPlanRepository(
        session, auto_commit=False
    )
    plan = subscription_plan_repository.get_subscription_plan_by_id(
        subscription_params.subscription_plan_id
    )
    if not plan:
        raise ValueError(
            f"Subscription plan {subscription_params.subscription_plan_id} does not exist"
        )
    if not plan.active:
        raise ValueError(
            f"Subscription plan {subscription_params.subscription_plan_id} is not active"
        )

    # Extract and validate subscription parameters
    start_date = subscription_params.start_date or datetime.now(UTC)
    end_date = subscription_params.end_date
    trial_start_date = subscription_params.trial_start_date
    payment_method = subscription_params.payment_method

    # Use plan defaults if not specified
    if trial_start_date is None and plan.free_trial_days and plan.free_trial_days > 0:
        trial_start_date = start_date
        start_date = trial_start_date + timedelta(days=plan.free_trial_days)

    # Check for overlapping subscriptions
    project_subscription_repository = ProjectSubscriptionRepository(
        session, auto_commit=False
    )
    has_overlap = project_subscription_repository.check_subscription_overlap(
        project_id, start_date, end_date
    )
    if has_overlap:
        raise ValueError(
            f"Project {project_id} already has an active subscription that overlaps with the requested dates"
        )

    # Determine initial status - always start as pending like account subscriptions
    # Status will be updated to trialing/active when Stripe subscription is created via checkout
    status = SubscriptionStatus.pending

    # Create the project subscription record
    external_id = uuid.uuid4()
    project_subscription = db.ProjectSubscription(
        id=uuid.uuid4(),
        external_id=external_id,
        version=1,
        project_id=project_id,
        subscription_id=external_id,  # For independent subscriptions
        subscription_plan_id=plan.id,
        payment_method=payment_method,
        trial_start_date=trial_start_date,
        start_date=start_date,
        end_date=end_date,
        status=status,
        deleted=False,
        recurring_credit_enabled=subscription_params.recurring_credit_enabled or False,
        recurring_credit_amount=subscription_params.recurring_credit_amount,
        recurring_credit_frequency=subscription_params.recurring_credit_frequency,
    )

    # Create Stripe product and prices (but NOT the subscription yet)
    # The Stripe subscription will be created via checkout session callback
    # This matches the account subscription flow
    if payment_method == PaymentMethod.autopay:
        # Ensure project has Stripe customer ID (project-level customer for independent subscriptions)
        if not project.stripe_customer_id:
            logger.info(
                "Project missing Stripe customer ID, creating one for independent subscription",
                extra={
                    "project_id": str(project.id),
                    "project_name": project.name,
                    "account_id": str(account.id),
                    "account_name": account.name,
                },
            )
            customer_info = create_stripe_customer_for_project(
                session, context, project, account
            )
            project.stripe_customer_id = customer_info.id

        # Create Stripe product for the project
        stripe_product_id = _stripe_product.create_product_for_project(
            project=project,
            account_name=account.name,
            plan_name=plan.name,
        )
        project_subscription.stripe_product_id = stripe_product_id

        logger.info(
            "Created Stripe product for project subscription",
            extra={
                "project_id": str(project_id),
                "product_id": stripe_product_id,
            },
        )

        # Create base price for monthly fee if applicable
        base_price_id = None
        if plan.monthly_fee and plan.monthly_fee > 0:
            base_price_id = _stripe_product.create_product_price(
                product_id=stripe_product_id,
                nickname="Base Monthly Fee",
                project=project,
                flat_fee=plan.monthly_fee,
            )
            project_subscription.base_price_id = base_price_id
            logger.info(
                "Created base price for project subscription",
                extra={
                    "project_id": str(project_id),
                    "price_id": base_price_id,
                    "amount": plan.monthly_fee,
                },
            )

        # Create metered billing for calls
        call_meter_id = _stripe_product.create_billing_meter(
            display_name=f"Calls - {project.name}",
            event_name=_stripe_product.get_call_meter_event_name(project_id),
        )

        call_tiers = _build_call_tiers(plan)
        call_price_id = _stripe_product.create_product_price(
            product_id=stripe_product_id,
            nickname="Call Usage",
            project=project,
            meter_tiers=call_tiers,
            meter_id=call_meter_id,
        )
        project_subscription.call_price_id = call_price_id

        logger.info(
            "Created call meter and price for project subscription",
            extra={
                "project_id": str(project_id),
                "meter_id": call_meter_id,
                "price_id": call_price_id,
            },
        )

        # Create metered billing for orders if applicable
        if plan.order_overage_charge:
            order_meter_id = _stripe_product.create_billing_meter(
                display_name=f"Orders - {project.name}",
                event_name=_stripe_product.get_order_meter_event_name(project_id),
            )

            order_tiers = _build_order_tiers(plan)
            order_price_id = _stripe_product.create_product_price(
                product_id=stripe_product_id,
                nickname="Order Usage",
                project=project,
                meter_tiers=order_tiers,
                meter_id=order_meter_id,
            )
            project_subscription.order_price_id = order_price_id

            logger.info(
                "Created order meter and price for project subscription",
                extra={
                    "project_id": str(project_id),
                    "meter_id": order_meter_id,
                    "price_id": order_price_id,
                },
            )

        # Note: Stripe subscription is NOT created here
        # It will be created later via checkout session callback (handle_stripe_checkout_success)
        # This matches the account subscription flow where products/prices are created first,
        # then the actual Stripe subscription is created during checkout
        logger.info(
            "Created Stripe products and prices for project subscription",
            extra={
                "project_id": str(project_id),
                "subscription_external_id": str(external_id),
                "stripe_product_id": stripe_product_id,
                "base_price_id": base_price_id,
                "call_price_id": call_price_id,
                "order_price_id": project_subscription.order_price_id,
                "note": "Stripe subscription will be created via checkout callback",
            },
        )

    # Save to database with change log
    with change_log_context(
        session=session,
        resource_type=ChangeResourceType.Subscription,
        author=context.email,
        account_id=account.id,
        resource_id=str(external_id),
        auto_commit=False,
    ) as ctx:
        created_subscription = (
            project_subscription_repository.create_project_subscription_with_prices(
                project_id=project_id,
                subscription_id=external_id,
                call_price_id=project_subscription.call_price_id,
                order_price_id=project_subscription.order_price_id,
            )
        )
        # Copy all the fields we set
        for field in [
            "external_id",
            "version",
            "subscription_plan_id",
            "stripe_product_id",
            "stripe_subscription_id",
            "payment_method",
            "base_price_id",
            "trial_start_date",
            "start_date",
            "end_date",
            "status",
            "recurring_credit_enabled",
            "recurring_credit_amount",
            "recurring_credit_frequency",
        ]:
            setattr(created_subscription, field, getattr(project_subscription, field))

        session.flush()
        session.refresh(created_subscription)
        ctx.new_record = created_subscription

    try:
        session.commit()
    except Exception as err:
        logger.error(f"Failed to create project subscription due to error: {err}")
        raise err

    logger.info(
        "Created project subscription",
        extra={
            "project_id": str(project_id),
            "subscription_external_id": str(external_id),
            "plan_id": str(plan.id),
            "status": status.value,
        },
    )

    # Send notification
    _send_project_subscription_activated_notification(
        session, account, project, created_subscription, plan
    )

    return created_subscription


def update_project_subscription(
    session: Session,
    context: UserContext,
    project_id: uuid.UUID,
    external_id: uuid.UUID,
    update_data: dict[str, Any],
    force_update: bool = False,
) -> db.ProjectSubscription:
    """
    Update a project subscription by creating a new version.

    IMPORTANT: This function performs DATABASE-ONLY updates and does NOT synchronize
    changes to Stripe. This is intentional for the following reasons:

    1. Subscription plan changes should use switch_subscription_plan() which handles
       Stripe synchronization including product/price creation and subscription item updates.

    2. Payment method changes in Stripe are handled through the Stripe dashboard or
       payment method update flows, not through subscription updates.

    3. Stripe subscription ID should never be manually updated; it's set during
       subscription creation or checkout success.

    4. Date/status changes are typically driven by Stripe webhooks or cancellation
       flows that handle both database and Stripe updates.

    This function is intended for administrative corrections, recurring credit updates,
    or other database-only metadata changes that don't require Stripe synchronization.

    Args:
        session: Database session
        context: User context for authorization and logging
        project_id: Project ID for authorization
        external_id: External ID of the subscription to update
        update_data: Fields to update (payment_method, trial_start_date, start_date,
                     end_date, status, stripe_subscription_id, subscription_plan_id,
                     recurring_credit_enabled, recurring_credit_amount,
                     recurring_credit_frequency)
        force_update: Whether to allow updates on non-active subscriptions

    Returns:
        New version of the project subscription

    Raises:
        ValueError: If subscription doesn't exist or validation fails

    Warning:
        Do not use this function to change subscription_plan_id for active Stripe
        subscriptions. Use switch_subscription_plan() instead to ensure proper
        Stripe synchronization.
    """
    project_subscription_repository = ProjectSubscriptionRepository(
        session, auto_commit=False
    )

    current_subscription = (
        project_subscription_repository.get_project_subscription_by_external_id(
            external_id
        )
    )
    if not current_subscription:
        raise ValueError(
            f"Project subscription with external_id {external_id} does not exist"
        )

    # Verify the subscription belongs to this project
    if current_subscription.project_id != project_id:
        raise ValueError(
            f"Subscription {external_id} does not belong to project {project_id}"
        )

    # Check if subscription is in valid state for updates
    if current_subscription.status not in [
        SubscriptionStatus.active,
        SubscriptionStatus.pending,
        SubscriptionStatus.trialing,
    ]:
        if force_update:
            logger.warning(f"Force updating project subscription {external_id}!")
        else:
            status_value = (
                current_subscription.status.value
                if current_subscription.status
                else "unknown"
            )
            raise ValueError(
                f"Cannot update subscription with status {status_value}. Use force_update=true to override."
            )

    # Get project for logging
    project = project_service.get_project(session, project_id)
    if not project:
        raise ValueError(f"Project {project_id} does not exist")

    # Duplicate the current subscription row, excluding id and timestamps
    cls = type(current_subscription)
    exclude_fields = ["id", "created_at", "updated_at"]
    data = {
        column.name: getattr(current_subscription, column.name)
        for column in cls.__table__.columns
        if column.name not in exclude_fields
    }
    new_subscription = cls(**data)

    allowed_fields = {
        "payment_method",
        "trial_start_date",
        "start_date",
        "end_date",
        "status",
        "stripe_subscription_id",
        "subscription_plan_id",
        "recurring_credit_enabled",
        "recurring_credit_amount",
        "recurring_credit_frequency",
    }

    nullable_fields = {"end_date", "trial_start_date", "stripe_subscription_id"}

    for k, v in update_data.items():
        if k in allowed_fields:
            if v is None and k not in nullable_fields:
                continue
            setattr(new_subscription, k, v)
    new_subscription.version = (new_subscription.version or 0) + 1

    # Cancel old version
    project_subscription_repository.update_project_subscription_status(
        external_id, SubscriptionStatus.cancelled
    )

    with change_log_context(
        session=session,
        resource_type=ChangeResourceType.Subscription,
        author=context.email,
        account_id=project.account_id,
        resource_id=str(external_id),
        old_record=copy.copy(current_subscription),
        auto_commit=False,
    ) as ctx:
        # Create new subscription (needs proper implementation)
        new_subscription.id = uuid.uuid4()
        session.add(new_subscription)
        session.flush()
        session.refresh(new_subscription)
        ctx.new_record = new_subscription

    try:
        session.commit()
    except Exception as err:
        logger.error(f"Failed to update project subscription due to error: {err}")
        raise err

    logger.info(
        "Updated project subscription",
        extra={
            "project_id": str(project_id),
            "subscription_external_id": str(external_id),
            "old_version": current_subscription.version,
            "new_version": new_subscription.version,
        },
    )

    return new_subscription


def update_project_subscription_status(
    session: Session,
    context: UserContext,
    project_id: uuid.UUID,
    external_id: uuid.UUID,
    new_status: SubscriptionStatus,
) -> db.ProjectSubscription:
    """
    Update the status of a project subscription.

    Args:
        session: Database session
        context: User context for authorization and logging
        project_id: Project ID for authorization
        external_id: External ID of the subscription to update
        new_status: New status to set

    Returns:
        Updated project subscription

    Raises:
        ValueError: If subscription doesn't exist
    """
    project_subscription_repository = ProjectSubscriptionRepository(
        session, auto_commit=True
    )

    current_subscription = (
        project_subscription_repository.get_project_subscription_by_external_id(
            external_id
        )
    )
    if not current_subscription:
        raise ValueError(
            f"Project subscription with external_id {external_id} does not exist"
        )

    # Verify the subscription belongs to this project
    if current_subscription.project_id != project_id:
        raise ValueError(
            f"Subscription {external_id} does not belong to project {project_id}"
        )

    # Get project for logging
    project = project_service.get_project(session, project_id)
    if not project:
        raise ValueError(f"Project {project_id} does not exist")

    old_subscription = copy.copy(current_subscription)

    try:
        with change_log_context(
            session=session,
            resource_type=ChangeResourceType.Subscription,
            author=context.email,
            account_id=project.account_id,
            resource_id=str(external_id),
            old_record=old_subscription,
            auto_commit=False,
        ) as ctx:
            updated_subscription = (
                project_subscription_repository.update_project_subscription_status(
                    external_id, new_status
                )
            )
            ctx.new_record = updated_subscription
    except Exception as e:
        logger.warning(
            f"Change log failed for project subscription status update, proceeding anyway: {e}"
        )
        updated_subscription = (
            project_subscription_repository.update_project_subscription_status(
                external_id, new_status
            )
        )

    if updated_subscription is None:
        raise ValueError(f"Failed to update project subscription {external_id}")

    logger.info(
        "Updated project subscription status",
        extra={
            "project_id": str(project_id),
            "subscription_external_id": str(external_id),
            "old_status": (
                old_subscription.status.value if old_subscription.status else None
            ),
            "new_status": new_status.value,
        },
    )

    return updated_subscription


def cancel_project_subscription(
    session: Session,
    context: UserContext,
    project_id: uuid.UUID,
    external_id: uuid.UUID,
) -> Optional[db.ProjectSubscription]:
    """
    Cancel a project subscription.

    This will:
    1. Update the subscription status to cancelled
    2. Cancel the Stripe subscription if it exists
    3. Send cancellation notification

    Args:
        session: Database session
        context: User context for authorization and logging
        project_id: Project ID for authorization
        external_id: External ID of the subscription to cancel

    Returns:
        Cancelled project subscription

    Raises:
        ValueError: If project or subscription doesn't exist
        RuntimeError: If Stripe cancellation fails
    """
    project = project_service.get_project(session, project_id)
    if not project:
        raise ValueError(f"Project {project_id} does not exist")

    project_subscription_repository = ProjectSubscriptionRepository(
        session, auto_commit=False
    )

    subscription_to_cancel = (
        project_subscription_repository.get_project_subscription_by_external_id(
            external_id
        )
    )
    if not subscription_to_cancel:
        raise ValueError(
            f"Project subscription with external_id {external_id} does not exist"
        )

    # Verify the subscription belongs to this project
    if subscription_to_cancel.project_id != project_id:
        raise ValueError(
            f"Subscription {external_id} does not belong to project {project_id}"
        )

    old_subscription = copy.copy(subscription_to_cancel)

    # Cancel Stripe subscription first if it exists
    if subscription_to_cancel.stripe_subscription_id:
        stripe_cancelled = _stripe_subscription.cancel_subscription(
            subscription_to_cancel.stripe_subscription_id
        )
        if not stripe_cancelled:
            raise RuntimeError(
                f"Failed to cancel Stripe subscription {subscription_to_cancel.stripe_subscription_id}. "
                "Internal subscription will not be cancelled to maintain data consistency."
            )
        logger.info(
            "Successfully cancelled Stripe subscription for project",
            extra={
                "project_id": str(project_id),
                "subscription_external_id": str(external_id),
                "stripe_subscription_id": subscription_to_cancel.stripe_subscription_id,
            },
        )

    # Update subscription status
    try:
        with change_log_context(
            session=session,
            resource_type=ChangeResourceType.Subscription,
            author=context.email,
            account_id=project.account_id,
            resource_id=str(external_id),
            old_record=old_subscription,
            auto_commit=False,
        ) as ctx:
            cancelled_subscription = (
                project_subscription_repository.update_project_subscription_status(
                    external_id,
                    SubscriptionStatus.cancelled,
                )
            )
            ctx.new_record = cancelled_subscription
    except Exception as e:
        logger.warning(
            f"Change log failed for project subscription cancellation, proceeding anyway: {e}"
        )
        cancelled_subscription = (
            project_subscription_repository.update_project_subscription_status(
                external_id,
                SubscriptionStatus.cancelled,
            )
        )

    try:
        session.commit()
    except Exception as err:
        logger.error(f"Failed to cancel project subscription due to error: {err}")
        raise err

    logger.info(
        f"Cancelled subscription for project {project.name}",
        extra={
            "project_id": str(project_id),
            "subscription_external_id": str(external_id),
            "stripe_subscription_id": subscription_to_cancel.stripe_subscription_id,
        },
    )

    # Send subscription cancelled notification
    if cancelled_subscription and subscription_to_cancel.subscription_plan_id:
        account = account_service.get_account_by_id(session, project.account_id)
        subscription_plan_repository = SubscriptionPlanRepository(session)
        plan = subscription_plan_repository.get_subscription_plan_by_id(
            subscription_to_cancel.subscription_plan_id
        )
        if plan and account:
            _send_project_subscription_cancelled_notification(
                session, account, project, cancelled_subscription, plan
            )

    return cancelled_subscription


def get_project_subscription_by_external_id(
    session: Session,
    external_id: uuid.UUID,
) -> db.ProjectSubscription | None:
    """Get a project subscription by external ID."""
    project_subscription_repository = ProjectSubscriptionRepository(
        session, auto_commit=True
    )
    return project_subscription_repository.get_project_subscription_by_external_id(
        external_id
    )


def get_active_project_subscription(
    session: Session,
    project_id: uuid.UUID,
) -> db.ProjectSubscription | None:
    """Get the active project subscription for a project."""
    project_subscription_repository = ProjectSubscriptionRepository(
        session, auto_commit=True
    )
    return project_subscription_repository.get_active_project_subscription(project_id)


def _send_project_subscription_activated_notification(
    session: Session,
    account: db.Account,
    project: db.Project,
    subscription: db.ProjectSubscription,
    plan: db.SubscriptionPlan,
) -> None:
    """Send project subscription activated notification."""
    try:
        # Calculate trial end date from subscription's trial_start_date + plan's free_trial_days
        trial_end_formatted = None
        if subscription.trial_start_date and plan.free_trial_days:
            trial_end = subscription.trial_start_date + timedelta(
                days=plan.free_trial_days
            )
            trial_end_formatted = trial_end.strftime("%B %d, %Y")

        event = BillingEvent(
            type=BillingEventType.SUBSCRIPTION_ACTIVATED,
            account_id=account.id,
            payload={
                "plan_name": plan.name,
                "project_name": project.name,
                "price": float(plan.monthly_fee or 0) / 100,  # Convert cents to dollars
                "currency": "USD",
                "trial_end": trial_end_formatted,
            },
        )
        handle_billing_event_sync(session, event)
    except Exception as e:
        logger.warning(
            f"Failed to send project subscription activated notification: {e}",
            extra={
                "project_id": str(project.id),
                "subscription_id": str(subscription.id),
            },
        )


def _send_project_subscription_cancelled_notification(
    session: Session,
    account: db.Account,
    project: db.Project,
    subscription: db.ProjectSubscription,
    plan: db.SubscriptionPlan,
) -> None:
    """Send project subscription cancelled notification."""
    try:
        # Calculate cancellation effective date
        cancel_date = subscription.end_date or datetime.now(UTC)
        event = BillingEvent(
            type=BillingEventType.SUBSCRIPTION_CANCELLED,
            account_id=account.id,
            payload={
                "plan_name": plan.name,
                "project_name": project.name,
                "cancel_effective_date": cancel_date.strftime("%B %d, %Y"),
            },
        )
        handle_billing_event_sync(session, event)
    except Exception as e:
        logger.warning(
            f"Failed to send project subscription cancelled notification: {e}",
            extra={
                "project_id": str(project.id),
                "subscription_id": str(subscription.id),
            },
        )
