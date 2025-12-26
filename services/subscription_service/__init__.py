import os

import stripe

from ._plan import (
    create_subscription_plan,
    delete_subscription_plan,
    get_subscription_plans,
    update_subscription_plan,
)
from ._stripe_subscription import (
    handle_subscription_deleted,
    sync_account_subscriptions,
    update_subscription_status_from_stripe,
)
from ._subscription import (
    cancel_account_subscription,
    create_account_subscription,
    create_project_subscription,
    create_stripe_checkout_url,
    create_stripe_customer_for_account,
    get_account_credit_balance,
    get_account_credit_grants,
    get_account_subscription,
    get_account_subscriptions,
    get_current_subscription,
    get_current_subscription_async,
    get_project_subscriptions_by_subscription_external_id,
    get_stripe_customer_id_for_project,
    get_stripe_customer_info_for_account,
    get_subscription_details,
    get_subscription_plan_by_id,
    grant_credit_to_account,
    handle_stripe_checkout_success,
    remove_project_subscription,
    should_block_calls_async,
    switch_subscription_plan,
    unlink_subscription_from_account,
    update_account_subscription,
    update_account_subscription_status,
    update_stripe_customer_for_account,
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
    "get_current_subscription_async",
    "get_subscription_plan_by_id",
    "get_subscription_details",
    "update_subscription_plan",
    "delete_subscription_plan",
    "create_stripe_checkout_url",
    "create_stripe_customer_for_account",
    "get_stripe_customer_info_for_account",
    "handle_stripe_checkout_success",
    "get_project_subscriptions_by_subscription_external_id",
    "create_project_subscription",
    "remove_project_subscription",
    "get_stripe_customer_id_for_project",
    "grant_credit_to_account",
    "get_account_credit_balance",
    "get_account_credit_grants",
    "should_block_calls_async",
    "switch_subscription_plan",
    "unlink_subscription_from_account",
    "update_stripe_customer_for_account",
    # Stripe sync functions
    "sync_account_subscriptions",
    "update_subscription_status_from_stripe",
    "handle_subscription_deleted",
]
