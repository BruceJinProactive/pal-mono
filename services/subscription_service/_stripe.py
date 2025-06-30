import json
import os
import uuid
from datetime import datetime

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
) -> Session:
    """
    Creates a new checkout session that allows user to subscribe to our product and
    automatically get charged the monthly fee by stripe.
    """
    redirect_url_prefix = redirect_url_prefix.rstrip("/")

    kwargs = {}
    if customer_email:
        kwargs["customer_email"] = customer_email

    try:
        return stripe.checkout.Session.create(
            mode="subscription",
            line_items=[
                {
                    "price": price_id,
                    "quantity": len(project_ids),
                }
            ],
            metadata={
                "project_ids": json.dumps([str(pid) for pid in project_ids]),
            },
            client_reference_id=str(account_id),
            success_url=f"{redirect_url_prefix}/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{redirect_url_prefix}/cancel",
            **kwargs,
        )
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


def parse_uuid(uuid_str: str | None) -> uuid.UUID:
    if uuid_str:
        try:
            return uuid.UUID(uuid_str)
        except ValueError:
            pass
    return uuid.UUID(int=0)
