import copy
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
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
from services.account_service import AccountParams
from services.history_service import change_log_context
from services.subscription_service import (
    _stripe_credit,
    _stripe_product,
    _stripe_subscription,
)
from services.subscription_service._stripe_product import MeterTier
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
    response = _stripe_subscription.handle_checkout_success(session_id)
    if not response:
        return response

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
        "Successfully updated subscription's stripe id",
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
    - Monthly end_date: start_date + 7 years (arbitrary and subject to change)
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
            "end_date": subscription.end_date.isoformat(),
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

    # Validate subscription doesn't already have a Stripe subscription ID
    if subscription.stripe_subscription_id:
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

    # Create checkout session with project-specific prices
    checkout_session = _stripe_subscription.create_checkout_session(
        account_id=account_id,
        customer_email=customer_email,
        subscription_external_id=subscription.external_id,
        line_items=line_items,
        redirect_url_prefix=redirect_url_prefix,
        start_date=subscription.start_date,
        existing_customer_id=existing_stripe_customer_id,
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
        raise ValueError(
            f"Project subscription does not exist for project {project_id} and subscription {subscription_id}"
        )

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

    return _stripe_credit.grant_credit_balance(
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

    return _stripe_credit.get_credit_balance(account.stripe_customer_id)


def get_account_credit_grants(
    account: db.Account,
) -> list[dict]:
    if not account.stripe_customer_id:
        raise ValueError(
            "Account does not have a stripe customer associated, does it have a subscription?"
        )

    return _stripe_credit.get_credit_grants_history(
        account.stripe_customer_id,
    )


def should_allow_calls(session: Session, account: db.Account) -> bool:
    if account.current_subscription_id is None:
        return True

    current_subscription = get_current_subscription(session, account)

    if not current_subscription:
        return False

    return current_subscription.status == SubscriptionStatus.active
