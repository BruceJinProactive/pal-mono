"""
Service for fetching comprehensive billing and subscription details.

This module provides functions to fetch detailed subscription information including:
- Usage metrics (calls used, overage, etc.)
- Invoice history
- Payment method information
- Upgrade/downgrade options with featured benefits
"""

import random
from datetime import datetime
from typing import List

import stripe
from sqlalchemy.orm import Session

import db
from api.schemas.admin.subscription import Invoice, UpgradeOption, UsageMetrics
from db.repositories.project_repository import ProjectRepository
from db.tables.types import TargetTier
from services.subscription_service._stripe_product import get_call_meter_event_name
from utils.log import logger

# Define tier ordering for sorting upgrade options
TIER_ORDER = {
    TargetTier.t1: 1,
    TargetTier.t2: 2,
    TargetTier.t3: 3,
    TargetTier.enterprise: 4,
}


def get_usage_metrics(
    session: Session,
    account: db.Account,
    subscription: db.AccountSubscription | None,
    stripe_customer_id: str | None,
) -> UsageMetrics:
    """
    Fetch usage metrics for the current billing period.

    Args:
        session: Database session
        account: Account to fetch metrics for
        subscription: Current subscription
        stripe_customer_id: Stripe customer ID

    Returns:
        UsageMetrics object with call usage and overage data
    """
    usage = UsageMetrics()

    # Get call quota from subscription plan
    if subscription and subscription.subscription_plan:
        usage.calls_included = subscription.subscription_plan.call_quota or 0

    if (
        not stripe_customer_id
        or not subscription
        or not subscription.stripe_subscription_id
    ):
        return usage

    try:
        # Get the current billing period from Stripe subscription
        stripe_sub = stripe.Subscription.retrieve(subscription.stripe_subscription_id)

        # Get period timestamps
        if not (hasattr(stripe_sub, "current_period_start") and hasattr(stripe_sub, "current_period_end")):  # type: ignore
            logger.warning(
                f"Stripe subscription missing period attributes for {subscription.stripe_subscription_id}"
            )
            return usage

        period_start = stripe_sub.current_period_start  # type: ignore
        period_end = stripe_sub.current_period_end  # type: ignore

        # Fetch meter event summaries for all projects under this account
        project_repo = ProjectRepository(session)
        projects = project_repo.get_projects_by_account_id(account.id)

        total_calls = 0
        for project in projects:
            event_name = get_call_meter_event_name(project.id)

            try:
                # Query meter event summaries for this project in the current billing period
                # Type ignore: Stripe's MeterEventSummary may not be in type stubs
                summaries = stripe.billing.MeterEventSummary.list(  # type: ignore
                    customer=stripe_customer_id,
                    event_name=event_name,
                    start_time=period_start,
                    end_time=period_end,
                )

                # Sum up the aggregated values
                for summary in summaries.auto_paging_iter():  # type: ignore
                    if hasattr(summary, "aggregated_value"):
                        total_calls += int(summary.aggregated_value)
            except Exception as e:
                logger.warning(
                    f"Failed to fetch meter events for project {project.id}: {e}"
                )
                continue

        usage.calls_used = total_calls
        usage.calls_overage = max(0, usage.calls_used - usage.calls_included)

        # Get overage charge from subscription plan (in cents)
        if (
            subscription.subscription_plan
            and subscription.subscription_plan.call_overage_charge
        ):
            overage_rate_dollars = (
                subscription.subscription_plan.call_overage_charge / 100
            )
            usage.overage_cost = usage.calls_overage * overage_rate_dollars

        logger.info(
            f"Fetched usage metrics for account {account.name}",
            extra={
                "account_id": str(account.id),
                "calls_used": usage.calls_used,
                "calls_included": usage.calls_included,
                "calls_overage": usage.calls_overage,
                "overage_cost": usage.overage_cost,
            },
        )
    except Exception as e:
        logger.error(
            f"Error fetching usage metrics: {e}",
            extra={"account_id": str(account.id)},
        )

    return usage


def get_recent_invoices(
    stripe_customer_id: str | None, limit: int = 10
) -> List[Invoice]:
    """
    Fetch recent invoices from Stripe.

    Args:
        stripe_customer_id: Stripe customer ID
        limit: Maximum number of invoices to return

    Returns:
        List of Invoice objects
    """
    invoices: List[Invoice] = []

    if not stripe_customer_id:
        return invoices

    try:
        stripe_invoices = stripe.Invoice.list(
            customer=stripe_customer_id,
            limit=limit,
        )

        for inv in stripe_invoices.data:
            # Skip invoices without required fields
            if not inv.id or not inv.status:
                continue

            invoices.append(
                Invoice(
                    id=inv.id,
                    invoice_number=inv.number,
                    amount_due=inv.amount_due,
                    amount_paid=inv.amount_paid,
                    currency=inv.currency,
                    status=inv.status,
                    created=datetime.fromtimestamp(inv.created),
                    due_date=(
                        datetime.fromtimestamp(inv.due_date) if inv.due_date else None
                    ),
                    invoice_pdf=inv.invoice_pdf,
                    hosted_invoice_url=inv.hosted_invoice_url,
                )
            )

        logger.info(
            f"Fetched {len(invoices)} invoices for customer {stripe_customer_id}"
        )
    except Exception as e:
        logger.error(
            f"Error fetching invoices: {e}",
            extra={"stripe_customer_id": stripe_customer_id},
        )

    return invoices


def get_upgrade_options(
    session: Session,
    current_plan_id: str | None,
    current_tier: TargetTier | None,
) -> List[UpgradeOption]:
    """
    Get upgrade/downgrade options with randomly selected featured benefits from database.

    Args:
        session: Database session
        current_plan_id: Current plan ID (UUID as string)
        current_tier: Current tier level (TargetTier enum)

    Returns:
        List of UpgradeOption objects with 3 randomly selected featured benefits
    """
    options: List[tuple[UpgradeOption, TargetTier]] = []

    # Fetch all active subscription plans from database
    from db.repositories.subscription_repository import SubscriptionPlanRepository

    repo = SubscriptionPlanRepository(session)
    all_plans = repo.get_subscription_plans(hidden=False)

    # Show upgrade options (higher tiers) and downgrades (lower tiers)
    for plan in all_plans:
        # Skip current plan
        if str(plan.id) == current_plan_id or plan.tier == current_tier:
            continue

        # Get all features for this plan from features_included
        all_features = plan.features_included or []

        # Randomly select 3 features to highlight
        featured_count = min(3, len(all_features))
        featured_benefits = (
            random.sample(all_features, featured_count) if all_features else []
        )

        # Convert monthly_fee from cents to dollars
        # Handle zero-dollar plans explicitly (free tiers should show $0, not None)
        price_monthly = plan.monthly_fee / 100 if plan.monthly_fee is not None else None

        options.append(
            (
                UpgradeOption(
                    plan_name=plan.name,
                    plan_id=str(plan.id),
                    price_monthly=price_monthly,
                    price_annual=None,  # Not currently tracked in database
                    featured_benefits=featured_benefits,
                ),
                plan.tier,
            )
        )

    # Sort by tier (ascending for upgrades first)
    options.sort(key=lambda x: TIER_ORDER.get(x[1], 999))

    # Return just the UpgradeOption objects without the tier
    return [option for option, _ in options]


def get_payment_method_info(
    stripe_customer_id: str | None,
) -> tuple[str | None, str | None, str | None]:
    """
    Get payment method information from Stripe.

    Args:
        stripe_customer_id: Stripe customer ID

    Returns:
        Tuple of (payment_status, last4, brand)
    """
    payment_status = None
    last4 = None
    brand = None

    if not stripe_customer_id:
        return payment_status, last4, brand

    try:
        # Fetch customer to get default payment method
        customer = stripe.Customer.retrieve(
            stripe_customer_id,
            expand=["invoice_settings.default_payment_method"],
        )

        # Get payment method details
        if (
            customer.invoice_settings
            and customer.invoice_settings.default_payment_method
        ):
            pm = customer.invoice_settings.default_payment_method
            # Type ignore: Stripe's type stubs may not include card attribute
            if hasattr(pm, "card") and pm.card:  # type: ignore
                last4 = pm.card.last4  # type: ignore
                brand = pm.card.brand  # type: ignore

        # Get subscription status as payment status
        subscriptions = stripe.Subscription.list(
            customer=stripe_customer_id,
            limit=1,
        )

        if subscriptions.data:
            payment_status = subscriptions.data[0].status

        logger.info(
            f"Fetched payment method for customer {stripe_customer_id}",
            extra={"last4": last4, "brand": brand, "status": payment_status},
        )
    except Exception as e:
        logger.error(
            f"Error fetching payment method: {e}",
            extra={"stripe_customer_id": stripe_customer_id},
        )

    return payment_status, last4, brand


def get_billing_cycle_info(
    stripe_subscription_id: str | None,
) -> tuple[str | None, datetime | None, datetime | None, datetime | None]:
    """
    Get billing cycle information.

    Args:
        stripe_subscription_id: Stripe subscription ID

    Returns:
        Tuple of (billing_cycle, next_billing_date, current_period_start, current_period_end)
    """
    billing_cycle = None
    next_billing_date = None
    current_period_start = None
    current_period_end = None

    if not stripe_subscription_id:
        return (
            billing_cycle,
            next_billing_date,
            current_period_start,
            current_period_end,
        )

    try:
        stripe_sub = stripe.Subscription.retrieve(stripe_subscription_id)

        # Determine billing cycle
        if stripe_sub.items and stripe_sub.items.data:
            price = stripe_sub.items.data[0].price
            if price.recurring:
                interval = price.recurring.interval
                billing_cycle = (
                    "monthly"
                    if interval == "month"
                    else "annual" if interval == "year" else interval
                )

        # Get billing dates
        # Type ignore: Stripe's type stubs may not include period attributes
        if hasattr(stripe_sub, "current_period_end") and stripe_sub.current_period_end:  # type: ignore
            next_billing_date = datetime.fromtimestamp(stripe_sub.current_period_end)  # type: ignore
            current_period_end = next_billing_date

        if hasattr(stripe_sub, "current_period_start") and stripe_sub.current_period_start:  # type: ignore
            current_period_start = datetime.fromtimestamp(
                stripe_sub.current_period_start  # type: ignore
            )

        logger.info(
            f"Fetched billing cycle info for subscription {stripe_subscription_id}",
            extra={
                "billing_cycle": billing_cycle,
                "next_billing_date": (
                    next_billing_date.isoformat() if next_billing_date else None
                ),
            },
        )
    except Exception as e:
        logger.error(
            f"Error fetching billing cycle: {e}",
            extra={"stripe_subscription_id": stripe_subscription_id},
        )

    return billing_cycle, next_billing_date, current_period_start, current_period_end
