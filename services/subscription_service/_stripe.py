import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict

import stripe
from stripe.checkout import Session

from services.subscription_service.schema import (
    StripeCheckoutResponse,
    StripeSubscriptionDetails,
)
from utils.log import logger

# Initialize the Stripe API key once, at module load
stripe.api_key = os.environ.get("STRIPE_API_KEY")


def create_checkout_session(
    account_id: uuid.UUID,
    project_ids: list[uuid.UUID],
    customer_email: str | None,
    price_id: str,
    redirect_url_prefix: str,
    start_date: datetime | None = None,
) -> Session:
    """
    Creates a new checkout session that allows user to subscribe to our product and
    automatically get charged the monthly fee by stripe.

    Args:
        account_id: UUID of the account creating the subscription
        project_ids: List of project UUIDs to associate with the subscription
        customer_email: Optional email for the customer
        price_id: Stripe price ID for the subscription
        redirect_url_prefix: URL prefix for success/cancel redirects
        start_date: Optional datetime when billing starts and trial ends.
                   If None, subscription begins immediately with no trial.

    Returns:
        Stripe checkout session object
    """
    redirect_url_prefix = redirect_url_prefix.rstrip("/")

    # Build subscription_data
    subscription_data_params: Dict[str, Any] = {
        "metadata": {
            "project_ids": json.dumps([str(pid) for pid in project_ids]),
        }
    }

    if start_date:
        # Set start date for both billing and trial end
        start_timestamp = int(start_date.timestamp())
        subscription_data_params["billing_cycle_anchor"] = start_timestamp
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
            "line_items": [
                {
                    "price": price_id,
                    "quantity": len(project_ids),
                }
            ],
            "subscription_data": subscription_data_params,
            "client_reference_id": str(account_id),
            "success_url": f"{redirect_url_prefix}/success?session_id={{CHECKOUT_SESSION_ID}}",
            "cancel_url": f"{redirect_url_prefix}/cancel",
        }
        if customer_email:
            session_params["customer_email"] = customer_email

        return stripe.checkout.Session.create(**session_params)
    except Exception as e:
        logger.error(f"Failed to create checkout session with stripe due to error: {e}")
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
    subscription_id = session.subscription

    try:
        subscription = stripe.Subscription.retrieve(id=str(subscription_id))
        project_ids = json.loads(subscription.metadata.get("project_ids", "[]"))
    except (stripe.StripeError, json.JSONDecodeError, KeyError) as e:
        logger.error(
            f"Failed to retrieve subscription details: {e}",
            extra={"subscription_id": subscription_id},
        )
        return None

    items = list(subscription.items.auto_paging_iter())

    if len(project_ids) != len(items):
        logger.error(
            "Mismatch between number of projects and number of subscription items!",
            extra={
                "session_id": session_id,
                "account_id": session.client_reference_id,
                "project_ids": project_ids,
                "num_items": len(items),
            },
        )
        return None

    for index, item in enumerate(items):
        stripe.SubscriptionItem.modify(
            item.id, metadata={"project_id": project_ids[index]}
        )

    return StripeCheckoutResponse(
        account_id=parse_uuid(session.client_reference_id),
        customer_id=str(subscription.customer),
        subscription_id=subscription.id,
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
            parse_uuid(item.get("metadata", {}).get("project_id", ""))
            for item in subscription.get("items", {}).get("data", [])
            if item.get("metadata", {}).get("project_id")
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


def parse_uuid(uuid_str: str | None) -> uuid.UUID:
    if uuid_str:
        try:
            return uuid.UUID(uuid_str)
        except ValueError:
            pass
    return uuid.UUID(int=0)
