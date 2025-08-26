import os

import stripe

from ._plan import (
    create_subscription_plan,
    delete_subscription_plan,
    get_subscription_plans,
    update_subscription_plan,
)
from ._subscription import (
    cancel_account_subscription,
    create_account_subscription,
    create_project_subscription,
    create_stripe_checkout_url,
    get_account_credit_balance,
    get_account_subscription,
    get_account_subscriptions,
    get_current_subscription,
    get_project_subscriptions_by_subscription_external_id,
    get_stripe_customer_id_for_project,
    get_subscription_plan_by_id,
    grant_credit_to_account,
    handle_stripe_checkout_success,
    remove_project_subscription,
    update_account_subscription,
    update_account_subscription_status,
)

# Initialize the Stripe API key once, at module load
stripe.api_key = os.environ.get("STRIPE_API_KEY")

__all__ = [
    "create_account_subscription",
    "get_account_subscriptions",
    "update_account_subscription",
    "create_subscription_plan",
    "update_account_subscription_status",
    "get_subscription_plans",
    "cancel_account_subscription",
    "get_current_subscription",
    "get_subscription_plan_by_id",
    "update_subscription_plan",
    "delete_subscription_plan",
    "create_stripe_checkout_url",
    "handle_stripe_checkout_success",
    "get_project_subscriptions_by_subscription_external_id",
    "create_project_subscription",
    "remove_project_subscription",
    "get_stripe_customer_id_for_project",
    "grant_credit_to_account",
    "get_account_credit_balance",
]
