import copy
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, List, Optional

import stripe
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
from services.subscription_service import _stripe_product, _stripe_subscription
from services.subscription_service._stripe_product import MeterTier
from services.subscription_service.schema import (
    StripeCheckoutResponse,
    SubscriptionParams,
)
from utils.log import logger


def handle_stripe_checkout_success(
    session: Session,
    context: UserContext,
    payment_intent_id: str,
    subscription_external_id: str,
) -> StripeCheckoutResponse | None:
    subscription = get_account_subscription_by_external_id(
        session, uuid.UUID(subscription_external_id)
    )
    if not subscription:
        logger.error(
            "Subscription not found",
            extra={"subscription_external_id": subscription_external_id},
        )
        return None

    response = _stripe_subscription.handle_checkout_success(
        payment_intent_id, subscription_external_id, str(subscription.account_id)
    )
    if not response:
        return response

    data = {
        "status": SubscriptionStatus.active,
    }
    update_account_subscription(
        session, context, response.account_id, response.subscription_external_id, data
    )
    logger.info(
        "Successfully updated subscription status to active",
        extra={
            "account_subscription_id": response.subscription_external_id,
            "payment_intent_id": payment_intent_id,
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

    # Step 1: Create a product on stripe for this account
    stripe_product_id = _stripe_product.create_product(account.name, plan.name)
    account_subscription.stripe_product_id = stripe_product_id

    # Step 2: Create the account subscription record
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

    # Step 3: add each project to the subscription
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
    stripe_product_id = subscription.stripe_product_id
    if not stripe_product_id:
        raise ValueError("Missing stripe product id in subscription.")

    plan = subscription_plan_repository.get_subscription_plan_by_id(
        subscription.subscription_plan_id
    )
    if not plan:
        raise ValueError("Subscription Plan not found.")
    project_subscription = project_subscription_repository.create_project_subscription(
        project.id,
        subscription.external_id,
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

    for project_sub in project_subscriptions:
        remove_project_subscription(
            session, project_sub.project_id, external_id, remove_subscription_item=False
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


def create_custom_checkout_data(
    session: Session,
    account_id: uuid.UUID,
    external_id: uuid.UUID,
    customer_email: str | None,
) -> dict | None:
    """
    Create structured data for custom checkout page with Payment Element.

    Args:
        session: Database session
        account_id: UUID of the account creating the subscription
        external_id: External ID of the subscription to create checkout for
        customer_email: Optional email for the customer

    Returns:
        Dict containing all checkout data or None if subscription not found
    """
    account_subscription_repository = AccountSubscriptionRepository(
        session, auto_commit=True
    )
    subscription_plan_repository = SubscriptionPlanRepository(session)

    subscription = account_subscription_repository.get_account_subscription(
        account_id, external_id
    )
    if not subscription:
        return None

    account = account_service.get_account_by_id(session, account_id)
    if not account:
        raise ValueError("Account not found")

    plan = subscription_plan_repository.get_subscription_plan_by_id(
        subscription.subscription_plan_id
    )
    if not plan:
        raise ValueError("Subscription plan not found")

    project_subscription_repository = ProjectSubscriptionRepository(
        session, auto_commit=True
    )
    project_subscriptions = (
        project_subscription_repository.get_project_subscriptions_by_subscription_id(
            external_id
        )
    )

    project_ids = [ps.project_id for ps in project_subscriptions]
    projects = project_service.get_projects_by_ids(session, project_ids)

    total_amount = len(projects) * (plan.monthly_fee or 0)

    payment_intent_params = {
        "amount": total_amount,
        "currency": "usd",
        "metadata": {
            "subscription_external_id": str(external_id),
            "account_id": str(account_id),
        },
        "automatic_payment_methods": {"enabled": True},
    }

    if customer_email:
        payment_intent_params["receipt_email"] = customer_email

    if account.stripe_customer_id:
        payment_intent_params["customer"] = account.stripe_customer_id

    try:
        payment_intent = stripe.PaymentIntent.create(**payment_intent_params)
    except stripe.StripeError as e:
        logger.error(
            f"Failed to create PaymentIntent: {e}",
            extra={
                "account_id": str(account_id),
                "subscription_id": str(external_id),
            },
        )
        raise

    return {
        "account": {
            "id": str(account.id),
            "name": account.name,
            "display_name": account.display_name or account.name,
            "total_projects": len(projects),
        },
        "subscription_plan": {
            "id": str(plan.id),
            "name": plan.name,
            "monthly_fee_per_project": plan.monthly_fee or 0,
            "currency": "USD",
            "call_quota_per_project": plan.call_quota or 0,
            "order_quota_per_project": plan.order_quota or 0,
            "call_overage_charge": plan.call_overage_charge or 0,
            "order_overage_charge": plan.order_overage_charge or 0,
        },
        "projects": [
            {
                "id": str(p.id),
                "name": p.name,
                "display_name": p.display_name or p.name,
            }
            for p in projects
        ],
        "pricing": {
            "billing_cycle": "monthly",
            "price_per_project": plan.monthly_fee or 0,
        },
        "payment": {
            "payment_intent_id": payment_intent.id,
            "client_secret": payment_intent.client_secret,
        },
    }


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
