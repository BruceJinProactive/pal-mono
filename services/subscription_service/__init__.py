import os

import stripe

from ._coupon import (
    assign_coupon_to_account,
    assign_coupon_to_project,
    get_account_coupon,
    get_project_coupon,
    remove_coupon_from_account,
    remove_coupon_from_project,
    update_account_coupon,
    update_project_coupon,
)
from ._plan import (
    create_subscription_plan,
    delete_subscription_plan,
    get_subscription_plans,
    update_subscription_plan,
)
from ._stripe_subscription import (
    create_subscription_direct,
    handle_subscription_deleted,
    sync_account_subscriptions,
    sync_subscription_from_stripe,
    update_subscription_status_from_stripe,
)
from ._subscription import (
    activate_subscription_without_payment_method,
    cancel_account_subscription,
    cancel_project_subscription,
    create_account_subscription,
    create_independent_project_subscription,
    create_project_subscription,
    create_stripe_checkout_url,
    create_stripe_checkout_url_for_project,
    create_stripe_customer_for_account,
    get_account_credit_balance,
    get_account_credit_grants,
    get_account_subscription,
    get_account_subscriptions,
    get_active_project_subscription,
    get_current_subscription,
    get_current_subscription_async,
    get_project_subscription_by_external_id,
    get_project_subscriptions_by_subscription_external_id,
    get_stripe_customer_id_for_project,
    get_stripe_customer_info_for_account,
    get_subscription_details,
    get_subscription_plan_by_id,
    grant_credit_to_account,
    handle_stripe_checkout_success,
    remove_project_subscription,
    should_block_calls_async,
    switch_project_subscription_plan,
    switch_subscription_plan,
    unlink_subscription_from_account,
    update_account_subscription,
    update_account_subscription_status,
    update_project_subscription,
    update_project_subscription_status,
    update_stripe_customer_for_account,
)

# Initialize the Stripe API key once, at module load
stripe.api_key = os.environ.get("STRIPE_API_KEY")

__all__ = [
    # Account subscription functions
    "create_account_subscription",
    "get_account_subscription",
    "get_account_subscriptions",
    "update_account_subscription",
    "update_account_subscription_status",
    "cancel_account_subscription",
    "get_current_subscription",
    "get_current_subscription_async",
    "get_subscription_details",
    # Project subscription functions (account-linked)
    "create_project_subscription",
    "remove_project_subscription",
    "get_project_subscriptions_by_subscription_external_id",
    # Project subscription functions (independent)
    "create_independent_project_subscription",
    "update_project_subscription",
    "update_project_subscription_status",
    "cancel_project_subscription",
    "get_project_subscription_by_external_id",
    "get_active_project_subscription",
    # Subscription plan functions
    "create_subscription_plan",
    "get_subscription_plans",
    "update_subscription_plan",
    "delete_subscription_plan",
    "get_subscription_plan_by_id",
    # Stripe functions
    "create_stripe_checkout_url",
    "create_stripe_checkout_url_for_project",
    "create_stripe_customer_for_account",
    "get_stripe_customer_info_for_account",
    "update_stripe_customer_for_account",
    "handle_stripe_checkout_success",
    "get_stripe_customer_id_for_project",
    # Credit functions
    "grant_credit_to_account",
    "get_account_credit_balance",
    "get_account_credit_grants",
    # Utility functions
    "should_block_calls_async",
    "switch_subscription_plan",
    "switch_project_subscription_plan",
    "unlink_subscription_from_account",
    # Direct subscription creation / activation
    "create_subscription_direct",
    "activate_subscription_without_payment_method",
    # Stripe sync functions
    "sync_account_subscriptions",
    "sync_subscription_from_stripe",
    "update_subscription_status_from_stripe",
    "handle_subscription_deleted",
    # Coupon management functions
    "assign_coupon_to_account",
    "update_account_coupon",
    "remove_coupon_from_account",
    "get_account_coupon",
    "assign_coupon_to_project",
    "update_project_coupon",
    "remove_coupon_from_project",
    "get_project_coupon",
]
