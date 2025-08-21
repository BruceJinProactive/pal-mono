import json
import uuid
from datetime import UTC, datetime
from typing import Any, Dict

import stripe
from stripe.checkout import Session

from services.subscription_service.schema import (
    StripeCheckoutResponse,
    StripeSubscriptionDetails,
)
from utils.log import logger

SUBSCRIPTION_EXTERNAL_ID = "subscription_external_id"
PROJECT_IDS = "project_ids"
REDIRECT_URL = "redirect_url"


def create_checkout_session(
    account_id: uuid.UUID,
    customer_email: str | None,
    subscription_external_id: uuid.UUID,
    line_items: list[dict],
    redirect_url_prefix: str,
    start_date: datetime | None = None,
) -> Session:
    """
    Creates a new checkout session that allows user to subscribe to our product and
    automatically get charged the monthly fee by stripe.

    Args:
        account_id: UUID of the account creating the subscription
        customer_email: Optional email for the customer
        line_items: List of Stripe line items for the checkout session.
        redirect_url_prefix: URL prefix for success/cancel redirects
        start_date: Optional datetime when billing starts and trial ends.
                   If None, subscription begins immediately with no trial.

    Returns:
        Stripe checkout session object
    """
    if not line_items:
        raise ValueError("line_items cannot be empty")

    for item in line_items:
        if not isinstance(item, dict):
            raise ValueError(f"Invalid line_item format: {item}")
        if "price" not in item and "price_data" not in item:
            raise ValueError(
                f"Line item must have either 'price' or 'price_data': {item}"
            )

    redirect_url_prefix = redirect_url_prefix.rstrip("/")

    # Build subscription_data
    subscription_data_params: Dict[str, Any] = {
        "metadata": {
            SUBSCRIPTION_EXTERNAL_ID: str(subscription_external_id),
            REDIRECT_URL: f"{redirect_url_prefix}/success",
        }
    }

    if start_date and start_date > datetime.now(UTC):
        # If start_date is in the future, then there is a trial.
        start_timestamp = int(start_date.timestamp())
        subscription_data_params["trial_end"] = start_timestamp

        logger.info(
            f"Setting subscription start date and trial end to {start_date.isoformat()}",
            extra={
                "account_id": str(account_id),
                "start_timestamp": start_timestamp,
            },
        )
    else:
        logger.info(
            "Creating subscription with immediate start and no trial",
            extra={"account_id": str(account_id)},
        )

    try:
        session_params = {
            "mode": "subscription",
            "line_items": line_items,
            "subscription_data": subscription_data_params,
            "client_reference_id": str(account_id),
            "success_url": f"{redirect_url_prefix}?action=payment_success&session_id={{CHECKOUT_SESSION_ID}}",
            "cancel_url": f"{redirect_url_prefix}?action=payment_cancelled",
        }
        if customer_email:
            session_params["customer_email"] = customer_email

        return stripe.checkout.Session.create(**session_params)
    except stripe.InvalidRequestError as e:
        error_msg = str(e)
        if "No such price" in error_msg:
            logger.error(
                f"Stripe checkout failed due to invalid price ID: {error_msg}",
                extra={
                    "account_id": str(account_id),
                    "subscription_id": str(subscription_external_id),
                    "line_items": line_items,
                    "stripe_error": error_msg,
                },
            )
            raise RuntimeError(
                f"Checkout session creation failed due to invalid Stripe price ID. "
                f"This usually means the project subscriptions have stale price IDs. "
                f"Error: {error_msg}"
            ) from e
        elif (
            "Quantity should not be specified where usage_type is `metered`"
            in error_msg
        ):
            logger.error(
                f"Stripe checkout failed due to quantity parameter on metered price: {error_msg}",
                extra={
                    "account_id": str(account_id),
                    "subscription_id": str(subscription_external_id),
                    "line_items": line_items,
                    "stripe_error": error_msg,
                },
            )
            raise RuntimeError(
                f"Checkout session creation failed because quantity was specified for metered prices. "
                f"Metered prices are billed based on usage events, not fixed quantities. "
                f"Error: {error_msg}"
            ) from e
        else:
            logger.error(
                f"Stripe checkout failed with invalid request: {e}",
                extra={
                    "account_id": str(account_id),
                    "subscription_id": str(subscription_external_id),
                    "line_items": line_items,
                },
            )
            raise e
    except Exception as e:
        logger.error(
            f"Failed to create checkout session with stripe due to error: {e}",
            extra={
                "account_id": str(account_id),
                "subscription_id": str(subscription_external_id),
                "line_items": line_items,
            },
        )
        raise e


def handle_checkout_success(
    session_id: str,
) -> StripeCheckoutResponse | None:
    """
    Updates metadata for each subscription item after a successful checkout.
    Links each subscription item to a specific project_id saved during subscription creation.
    """
    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except stripe.StripeError as e:
        logger.error(
            f"Failed to retrieve checkout session: {e}",
            extra={"session_id": session_id},
        )
        return None

    if not session.subscription:
        logger.error(
            "No subscription found in the session!", extra={"session_id": session_id}
        )
        return None
    subscription_id = str(session.subscription)

    try:
        subscription = stripe.Subscription.retrieve(id=subscription_id)
    except (stripe.StripeError, json.JSONDecodeError, KeyError) as e:
        logger.error(
            f"Failed to retrieve subscription details: {e}",
            extra={"subscription_id": subscription_id},
        )
        return None

    external_id = parse_uuid(subscription.metadata.get(SUBSCRIPTION_EXTERNAL_ID))

    logger.info("Successfully handled stripe checkout success event")
    return StripeCheckoutResponse(
        account_id=parse_uuid(session.client_reference_id),
        customer_id=str(subscription.customer),
        stripe_subscription_id=subscription_id,
        subscription_external_id=external_id,
    )


def get_subscription_details(
    subscription_id: str,
):
    try:
        subscription = stripe.Subscription.retrieve(
            subscription_id, expand=["items.data"]
        )
        customer_id = str(subscription.customer)
        invoice = stripe.Invoice.create_preview(customer=customer_id)

        project_ids = [
            parse_uuid(item.get("metadata", {}).get(PROJECT_IDS, ""))
            for item in subscription.get("items", {}).get("data", [])
            if item.get("metadata", {}).get(PROJECT_IDS)
        ]
    except stripe.StripeError as e:
        logger.error(
            f"Stripe API error retrieving subscription details: {e}",
            extra={"subscription_id": subscription_id},
        )
        return None
    except Exception as e:
        logger.error(
            f"Unexpected error retrieving subscription details: {e}",
            extra={"subscription_id": subscription_id},
        )
        return None

    return StripeSubscriptionDetails(
        subscription_id=subscription_id,
        status=subscription.status,
        collection_method=subscription.collection_method,
        billing_cycle_anchor=datetime.fromtimestamp(subscription.billing_cycle_anchor),
        current_period_charge=invoice.amount_due,
        included_project_ids=project_ids,
    )


def add_project_to_subscription(
    subscription_id: str, new_project_id: uuid.UUID, price_id: str
):
    try:
        stripe.SubscriptionItem.create(
            subscription=subscription_id,
            price=price_id,
            metadata={"project_id": str(new_project_id)},
            proration_behavior="create_prorations",
        )
        logger.info(
            "Successfully added project to subscription",
            extra={"subscription_id": subscription_id, "project_id": new_project_id},
        )
    except stripe.StripeError as e:
        logger.error(
            f"Failed to add project to subscription: {e}",
            extra={"subscription_id": subscription_id, "project_id": new_project_id},
        )
        raise


def remove_project_from_subscription(
    subscription_id: str, old_project_id: uuid.UUID, price_id: str
):
    try:
        subscription = stripe.Subscription.retrieve(subscription_id, expand=["items"])
    except stripe.StripeError as e:
        logger.error(
            f"Failed to retrieve subscription: {e}",
            extra={"subscription_id": subscription_id},
        )
        return

    target_item = None
    for item in subscription.get("items", {}).get("data", []):
        if item.get("metadata", {}).get("project_id") == str(old_project_id):
            target_item = item
            break

    if not target_item:
        logger.warning(
            "Failed to locate matching item from subscription.",
            extra={
                "subscription_id": subscription_id,
                "project_id": old_project_id,
            },
        )
        return

    try:
        stripe.SubscriptionItem.delete(target_item.id)
    except stripe.StripeError as e:
        logger.error(
            f"Failed to delete subscription item: {e}",
            extra={
                "subscription_id": subscription_id,
                "project_id": old_project_id,
            },
        )
        return
    logger.info(
        "Successfully deleted subscription item",
        extra={
            "subscription_id": subscription_id,
            "project_id": old_project_id,
        },
    )


def update_subscription_quantity(
    subscription_id: str, price_id: str, new_quantity: int
) -> bool:
    """
    Update the quantity of a subscription item that matches the given price_id.

    Args:
        subscription_id: The Stripe subscription ID
        price_id: The price ID to match against subscription items
        new_quantity: The new quantity to set

    Returns:
        bool: True if update was successful, False otherwise
    """
    try:
        # Retrieve the subscription with expanded items
        subscription = stripe.Subscription.retrieve(subscription_id, expand=["items"])

        if not subscription.items or not subscription.items.data:
            logger.warning(
                "No subscription items found",
                extra={"subscription_id": subscription_id},
            )
            return False

        # Find the subscription item that matches the price_id
        target_item = None
        for item in subscription.items.data:
            if item.price.id == price_id:
                target_item = item
                break

        if not target_item:
            logger.warning(
                f"No subscription item found with price_id {price_id}",
                extra={
                    "subscription_id": subscription_id,
                    "price_id": price_id,
                },
            )
            return False

        # Update the quantity of the subscription item
        stripe.SubscriptionItem.modify(
            target_item.id,
            quantity=new_quantity,
            proration_behavior="create_prorations",
        )

        logger.info(
            "Successfully updated subscription item quantity",
            extra={
                "subscription_id": subscription_id,
                "price_id": price_id,
                "old_quantity": target_item.quantity,
                "new_quantity": new_quantity,
                "item_id": target_item.id,
            },
        )

        return True

    except stripe.StripeError as e:
        logger.error(
            f"Failed to update subscription quantity: {e}",
            extra={
                "subscription_id": subscription_id,
                "price_id": price_id,
                "new_quantity": new_quantity,
            },
        )
        return False
    except Exception as e:
        logger.error(
            f"Unexpected error updating subscription quantity: {e}",
            extra={
                "subscription_id": subscription_id,
                "price_id": price_id,
                "new_quantity": new_quantity,
            },
        )
        return False


def cancel_subscription(subscription_id: str, cancel_immediately: bool = False) -> bool:
    """
    Cancels a Stripe subscription.

    Args:
        subscription_id: The Stripe subscription ID to cancel
        cancel_immediately: If True, cancels immediately. If False, cancels at period end.

    Returns:
        bool: True if cancellation was successful, False otherwise
    """
    try:
        if cancel_immediately:
            # Cancel immediately
            cancelled_subscription = stripe.Subscription.cancel(subscription_id)
            logger.info(
                "Successfully cancelled subscription immediately",
                extra={
                    "subscription_id": subscription_id,
                    "status": cancelled_subscription.status,
                },
            )
        else:
            # Cancel at period end (default behavior)
            updated_subscription = stripe.Subscription.modify(
                subscription_id, cancel_at_period_end=True
            )
            logger.info(
                "Successfully scheduled subscription for cancellation at period end",
                extra={
                    "subscription_id": subscription_id,
                    "cancel_at_period_end": updated_subscription.cancel_at_period_end,
                },
            )
        return True
    except stripe.StripeError as e:
        logger.error(
            f"Failed to cancel subscription: {e}",
            extra={
                "subscription_id": subscription_id,
                "cancel_immediately": cancel_immediately,
            },
        )
        return False
    except Exception as e:
        logger.error(
            f"Unexpected error cancelling subscription: {e}",
            extra={
                "subscription_id": subscription_id,
                "cancel_immediately": cancel_immediately,
            },
        )
        return False


def add_subscription_item(
    stripe_subscription_id: str,
    stripe_price_id: str,
):
    try:
        stripe.SubscriptionItem.create(
            subscription=stripe_subscription_id,
            price=stripe_price_id,
            proration_behavior="create_prorations",
        )
    except Exception as err:
        logger.error(f"Failed to add subscription item due to error: {err}")
        raise err


def remove_subscription_item(
    stripe_subscription_id: str,
    stripe_price_id: str,
):
    try:
        # 1. Retrieve subscription to find matching subscription item
        subscription = stripe.Subscription.retrieve(
            stripe_subscription_id, expand=["items.data.price"]
        )

        subscription_item_id = None
        for item in subscription["items"].data:
            if item and item.price.id == stripe_price_id:
                subscription_item_id = item.id
                break

        if not subscription_item_id:
            raise ValueError(
                f"Price {stripe_price_id} not found in subscription {stripe_subscription_id}"
            )

        # 2. Delete the subscription item
        stripe.SubscriptionItem.delete(
            subscription_item_id, proration_behavior="create_prorations"
        )
        logger.info(
            "Successfully removed item from subscription",
            extra={
                "price_id": stripe_price_id,
                "subscription_id": stripe_subscription_id,
            },
        )
    except Exception as err:
        logger.error(f"Failed to remove subscription item due to error: {err}")
        raise err


def update_subscription(
    subscription_id: str,
    trial_end_date: datetime | None = None,
    payment_method: str | None = None,
    new_price_id: str | None = None,
) -> bool:
    """
    Updates a Stripe subscription with new parameters.

    Args:
        subscription_id: The Stripe subscription ID to update
        trial_end_date: Optional new trial end date. If provided, extends or modifies the trial period.
        payment_method: Optional new payment method ID to set as default
        new_price_id: Optional new price ID to change the monthly fee

    Returns:
        bool: True if update was successful, False otherwise
    """
    try:
        update_params = {}

        # Update trial end date if provided
        if trial_end_date:
            if trial_end_date > datetime.now(UTC):
                update_params["trial_end"] = int(trial_end_date.timestamp())
                logger.info(
                    f"Updating subscription trial end to {trial_end_date.isoformat()}",
                    extra={"subscription_id": subscription_id},
                )
            else:
                logger.warning(
                    "Trial end date is in the past, skipping trial update",
                    extra={"subscription_id": subscription_id},
                )
        # Update payment method if provided
        if payment_method:
            update_params["default_payment_method"] = payment_method
            logger.info(
                "Updating subscription payment method",
                extra={
                    "subscription_id": subscription_id,
                    "payment_method": payment_method,
                },
            )

        # Update price/monthly fee if provided
        if new_price_id:
            # First, get the current subscription to find the subscription item
            subscription = stripe.Subscription.retrieve(
                subscription_id, expand=["items"]
            )

            # Update the first subscription item with the new price
            # Note: This assumes a single subscription item. For multiple items,
            # you might need more complex logic
            if subscription.items and subscription.items.data:
                subscription_item = subscription.items.data[0]
                stripe.SubscriptionItem.modify(
                    subscription_item.id,
                    price=new_price_id,
                    proration_behavior="create_prorations",
                )
                logger.info(
                    "Updated subscription item price",
                    extra={
                        "subscription_id": subscription_id,
                        "new_price_id": new_price_id,
                        "item_id": subscription_item.id,
                    },
                )

        # Apply subscription-level updates if any
        if update_params:
            updated_subscription = stripe.Subscription.modify(
                subscription_id, **update_params
            )
            logger.info(
                "Successfully updated subscription",
                extra={
                    "subscription_id": subscription_id,
                    "updated_fields": list(update_params.keys()),
                    "status": updated_subscription.status,
                },
            )

        return True

    except stripe.StripeError as e:
        logger.error(
            f"Failed to update subscription: {e}",
            extra={
                "subscription_id": subscription_id,
                "trial_end_date": trial_end_date,
                "payment_method": payment_method,
                "new_price_id": new_price_id,
            },
        )
        return False
    except Exception as e:
        logger.error(
            f"Unexpected error updating subscription: {e}",
            extra={
                "subscription_id": subscription_id,
                "trial_end_date": trial_end_date,
                "payment_method": payment_method,
                "new_price_id": new_price_id,
            },
        )
        return False


def parse_uuid(uuid_str: str | None) -> uuid.UUID:
    if uuid_str:
        try:
            return uuid.UUID(uuid_str)
        except ValueError:
            pass
    return uuid.UUID(int=0)
