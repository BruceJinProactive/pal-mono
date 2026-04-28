import json
import uuid
from datetime import UTC, datetime, timezone
from typing import Any, Dict, Optional

import stripe
from sqlalchemy.ext.asyncio import AsyncSession
from stripe.checkout import Session
from typing_extensions import Literal

from db.repositories.account_repository import AccountRepository
from db.repositories.project_repository import ProjectRepository
from db.repositories.subscription_repository import (
    AsyncAccountSubscriptionRepository,
    AsyncProjectSubscriptionRepository,
)
from db.tables.types import SubscriptionStatus
from services.subscription_service.schema import (
    StripeCheckoutResponse,
    StripeSubscriptionDetails,
)
from utils.log import logger


def create_stripe_coupon(
    coupon_id: str | None = None,
    percent_off: float | None = None,
    amount_off: int | None = None,
    currency: str | None = None,
    duration: str = "once",
    duration_in_months: int | None = None,
    max_redemptions: int | None = None,
    redeem_by: int | None = None,
    name: str | None = None,
    metadata: dict[str, str] | None = None,
) -> stripe.Coupon:
    """
    Create a new Stripe coupon.

    Args:
        coupon_id: Optional custom ID for the coupon (auto-generated if not provided)
        percent_off: Percentage discount (0-100). Mutually exclusive with amount_off
        amount_off: Fixed amount discount in cents. Mutually exclusive with percent_off
        currency: Currency for amount_off (required if amount_off is specified)
        duration: How long the coupon lasts - 'once', 'repeating', or 'forever'
        duration_in_months: Required if duration is 'repeating'
        max_redemptions: Maximum number of times this coupon can be redeemed
        redeem_by: Unix timestamp for coupon expiration
        name: Human-readable name for the coupon
        metadata: Additional metadata to attach to the coupon

    Returns:
        Created Stripe coupon object

    Raises:
        ValueError: If validation fails or invalid parameters provided
    """
    # Validate that either percent_off or amount_off is provided, but not both
    if percent_off is None and amount_off is None:
        raise ValueError("Either percent_off or amount_off must be provided")

    if percent_off is not None and amount_off is not None:
        raise ValueError("Cannot specify both percent_off and amount_off")

    # Validate percent_off range
    if percent_off is not None and (percent_off <= 0 or percent_off > 100):
        raise ValueError("percent_off must be between 0 and 100")

    # Validate amount_off requires currency
    if amount_off is not None:
        if not currency:
            raise ValueError("currency is required when amount_off is specified")
        if amount_off <= 0:
            raise ValueError("amount_off must be positive")

    # Validate duration
    valid_durations = ["once", "repeating", "forever"]
    if duration not in valid_durations:
        raise ValueError(f"duration must be one of: {valid_durations}")

    # Validate duration_in_months for repeating coupons
    if duration == "repeating":
        if not duration_in_months or duration_in_months <= 0:
            raise ValueError(
                "duration_in_months is required and must be positive for repeating coupons"
            )

    # Build coupon parameters
    coupon_params: dict[str, Any] = {
        "duration": duration,
    }

    if coupon_id:
        coupon_params["id"] = coupon_id

    if percent_off is not None:
        coupon_params["percent_off"] = percent_off

    if amount_off is not None:
        coupon_params["amount_off"] = amount_off
        coupon_params["currency"] = currency

    if duration_in_months:
        coupon_params["duration_in_months"] = duration_in_months

    if max_redemptions:
        coupon_params["max_redemptions"] = max_redemptions

    if redeem_by:
        coupon_params["redeem_by"] = redeem_by

    if name:
        coupon_params["name"] = name

    if metadata:
        coupon_params["metadata"] = metadata

    try:
        coupon = stripe.Coupon.create(**coupon_params)

        logger.info(
            f"Created Stripe coupon: {coupon.id}",
            extra={
                "coupon_id": coupon.id,
                "duration": coupon.duration,
                "percent_off": coupon.percent_off,
                "amount_off": coupon.amount_off,
                "name": name,
            },
        )

        return coupon

    except stripe.InvalidRequestError as e:
        error_msg = str(e)
        logger.error(
            f"Invalid request when creating coupon: {e}",
            extra={"error": error_msg, "params": coupon_params},
        )
        raise ValueError(f"Failed to create coupon: {error_msg}")
    except stripe.StripeError as e:
        logger.error(f"Stripe error creating coupon: {e}", extra={"error": str(e)})
        raise ValueError(f"Failed to create coupon: {str(e)}")


def validate_stripe_coupon(coupon_id: str) -> bool:
    """
    Validate that a Stripe coupon exists and is active.

    Args:
        coupon_id: The Stripe coupon ID to validate

    Returns:
        True if coupon is valid and active, False otherwise

    Raises:
        ValueError: If coupon validation fails with specific error message
    """
    try:
        coupon = stripe.Coupon.retrieve(coupon_id)

        if not coupon.valid:
            raise ValueError(f"Coupon '{coupon_id}' is not valid")

        # Check if coupon has expiration and if it's expired
        if coupon.redeem_by and coupon.redeem_by < int(datetime.now(UTC).timestamp()):
            raise ValueError(f"Coupon '{coupon_id}' has expired")

        # Check if coupon has max redemptions and is exhausted
        if coupon.max_redemptions and coupon.times_redeemed >= coupon.max_redemptions:
            raise ValueError(f"Coupon '{coupon_id}' has reached maximum redemptions")

        logger.debug(
            "Validated Stripe coupon: %s",
            coupon_id,
        )
        return True

    except stripe.InvalidRequestError as e:
        if e.code == "resource_missing":
            raise ValueError(f"Coupon '{coupon_id}' does not exist")
        raise ValueError(f"Invalid coupon '{coupon_id}': {str(e)}")
    except stripe.StripeError as e:
        logger.error(
            f"Stripe error validating coupon: {e}", extra={"coupon_id": coupon_id}
        )
        raise ValueError(f"Failed to validate coupon '{coupon_id}': {str(e)}")


def list_stripe_coupons(session: Any, limit: int = 100) -> list[dict[str, Any]]:
    """
    List all Stripe coupons with information about which accounts/projects use them.

    Args:
        session: Database session for querying account/project usage
        limit: Maximum number of coupons to return (default 100, max 100)

    Returns:
        List of coupon details dictionaries including account_names and project_names

    Raises:
        ValueError: If Stripe API call fails
    """
    try:
        # Limit to max 100 as per Stripe API limits
        limit = min(limit, 100)

        coupons = stripe.Coupon.list(limit=limit)

        account_repo = AccountRepository(session)
        project_repo = ProjectRepository(session)

        # Get all accounts with coupons using repository methods
        accounts_with_coupons = account_repo.get_accounts_with_coupons()

        # Get all projects with coupons using repository methods
        projects_with_coupons = project_repo.get_projects_with_coupons()

        # Build lookup dictionaries
        coupon_to_accounts = {}
        for account in accounts_with_coupons:
            coupon_id = account.stripe_coupon_id
            if coupon_id not in coupon_to_accounts:
                coupon_to_accounts[coupon_id] = []
            coupon_to_accounts[coupon_id].append(account.name)

        coupon_to_projects = {}
        for project in projects_with_coupons:
            coupon_id = project.stripe_coupon_id
            if coupon_id not in coupon_to_projects:
                coupon_to_projects[coupon_id] = []
            coupon_to_projects[coupon_id].append(project.name)

        coupon_list = []
        for coupon in coupons.auto_paging_iter():
            coupon_details = {
                "id": coupon.id,
                "name": coupon.name,
                "percent_off": coupon.percent_off,
                "amount_off": coupon.amount_off,
                "currency": coupon.currency,
                "duration": coupon.duration,
                "duration_in_months": coupon.duration_in_months,
                "max_redemptions": coupon.max_redemptions,
                "times_redeemed": coupon.times_redeemed,
                "valid": coupon.valid,
                "redeem_by": coupon.redeem_by,
                "created": coupon.created,
                "account_names": coupon_to_accounts.get(coupon.id, []),
                "project_names": coupon_to_projects.get(coupon.id, []),
            }
            coupon_list.append(coupon_details)

            # Stop if we've reached the limit
            if len(coupon_list) >= limit:
                break

        logger.info(
            f"Retrieved {len(coupon_list)} Stripe coupons with usage info",
            extra={"count": len(coupon_list)},
        )

        return coupon_list

    except stripe.StripeError as e:
        logger.error(f"Stripe error listing coupons: {e}", extra={"error": str(e)})
        raise ValueError(f"Failed to list coupons: {str(e)}")


# Map Stripe subscription statuses to internal SubscriptionStatus enum
STRIPE_STATUS_MAP: dict[str, SubscriptionStatus] = {
    "active": SubscriptionStatus.active,
    "trialing": SubscriptionStatus.trialing,
    "past_due": SubscriptionStatus.past_due,
    "unpaid": SubscriptionStatus.unpaid,
    "canceled": SubscriptionStatus.cancelled,
    "incomplete": SubscriptionStatus.pending,
    "incomplete_expired": SubscriptionStatus.expired,
    "paused": SubscriptionStatus.pending,
}

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
    existing_customer_id: str | None = None,
    referral_code: str | None = None,
    account_coupon_id: str | None = None,
    subscription_type: str = "account",
    project_id: uuid.UUID | None = None,
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
        existing_customer_id: Optional existing Stripe customer ID to reuse
        referral_code: Optional Rewardful referral token from ?via= parameter
        account_coupon_id: Optional Stripe coupon ID from account to apply to the subscription.
                          Supports both one-time and recurring coupons.
        subscription_type: Type of subscription - "account" or "project" (default: "account")
        project_id: Optional project UUID (required if subscription_type is "project")

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
    subscription_metadata = {
        SUBSCRIPTION_EXTERNAL_ID: str(subscription_external_id),
        REDIRECT_URL: f"{redirect_url_prefix}/success",
    }

    # Add Rewardful referral code if present
    if referral_code:
        subscription_metadata["rewardful_referral"] = referral_code

    # Add coupon to metadata for tracking
    if account_coupon_id:
        subscription_metadata["coupon_id"] = account_coupon_id

    subscription_data_params: Dict[str, Any] = {"metadata": subscription_metadata}

    # Apply coupon to the subscription when it's created by Stripe Checkout
    if account_coupon_id:
        try:
            validate_stripe_coupon(account_coupon_id)
            subscription_data_params["coupon"] = account_coupon_id
            logger.info(
                f"Coupon {account_coupon_id} will be applied to subscription created by checkout",
                extra={
                    "account_id": str(account_id),
                    "coupon_id": account_coupon_id,
                },
            )
        except ValueError as e:
            logger.error(
                f"Coupon validation failed: {e}",
                extra={
                    "account_id": str(account_id),
                    "coupon_id": account_coupon_id,
                },
            )
            raise

    if start_date and start_date > datetime.now(UTC):
        # If start_date is in the future, then there is a trial.
        start_timestamp = int(start_date.timestamp())
        subscription_data_params["trial_end"] = start_timestamp

        logger.debug(
            "Setting subscription start date and trial end to %s",
            start_date.isoformat(),
            extra={
                "account_id": str(account_id),
                "start_timestamp": start_timestamp,
            },
        )

    try:
        # Build checkout session metadata
        checkout_metadata = {
            "subscription_type": subscription_type,
            "subscription_external_id": str(subscription_external_id),
        }

        if referral_code:
            checkout_metadata["rewardful_referral"] = referral_code

        if project_id:
            checkout_metadata["project_id"] = str(project_id)

        session_params = {
            "mode": "subscription",
            "line_items": line_items,
            "subscription_data": subscription_data_params,
            "client_reference_id": str(account_id),
            "success_url": f"{redirect_url_prefix}?action=payment_success&session_id={{CHECKOUT_SESSION_ID}}",
            "cancel_url": f"{redirect_url_prefix}?action=payment_cancelled",
            "payment_method_types": ["card", "us_bank_account"],
        }

        # Always add metadata to checkout session
        session_params["metadata"] = checkout_metadata

        if existing_customer_id:
            session_params["customer"] = existing_customer_id
            session_params["customer_update"] = {"name": "auto"}

            # Update existing customer with referral code metadata
            if referral_code:
                try:
                    existing_customer = stripe.Customer.retrieve(existing_customer_id)
                    updated_metadata = (
                        dict(existing_customer.metadata)
                        if existing_customer.metadata
                        else {}
                    )
                    updated_metadata["rewardful_referral"] = referral_code

                    stripe.Customer.modify(
                        existing_customer_id, metadata=updated_metadata
                    )
                    logger.info(
                        f"Updated Stripe customer {existing_customer_id} with referral code: {referral_code}"
                    )
                except stripe.StripeError as e:
                    logger.warning(
                        f"Failed to update customer metadata with referral code: {e}",
                        extra={"customer_id": existing_customer_id},
                    )
        elif customer_email:
            session_params["customer_email"] = customer_email
            # For new customers, Stripe will auto-create the customer
            # The subscription metadata will be inherited by the customer
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

    # Check metadata for subscription type and project_id (handle None metadata)
    subscription_type = (
        session.metadata.get("subscription_type", "account")
        if session.metadata
        else "account"
    )
    project_id_str = session.metadata.get("project_id") if session.metadata else None
    project_id = parse_uuid(project_id_str) if project_id_str else None

    logger.info(
        "Successfully handled stripe checkout success event",
        extra={
            "subscription_type": subscription_type,
            "project_id": str(project_id) if project_id else None,
            "external_id": str(external_id),
        },
    )

    return StripeCheckoutResponse(
        account_id=parse_uuid(session.client_reference_id),
        customer_id=str(subscription.customer),
        stripe_subscription_id=subscription_id,
        subscription_external_id=external_id,
        subscription_type=subscription_type,
        project_id=project_id,
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
    proration_behavior: Literal[
        "always_invoice", "create_prorations", "none"
    ] = "create_prorations",
):
    try:
        stripe.SubscriptionItem.create(
            subscription=stripe_subscription_id,
            price=stripe_price_id,
            proration_behavior=proration_behavior,
        )
    except Exception as err:
        logger.error(f"Failed to add subscription item due to error: {err}")
        raise err


def remove_subscription_item(
    stripe_subscription_id: str,
    stripe_price_id: str,
    proration_behavior: Literal[
        "always_invoice", "create_prorations", "none"
    ] = "create_prorations",
    ignore_if_not_found: bool = True,
):
    """
    Remove a subscription item from a Stripe subscription.

    Args:
        stripe_subscription_id: Stripe subscription ID
        stripe_price_id: Price ID to remove
        proration_behavior: How to handle prorations
        ignore_if_not_found: If True, log warning instead of raising error when price not found

    Raises:
        ValueError: If price not found and ignore_if_not_found is False
    """
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
            if ignore_if_not_found:
                logger.warning(
                    f"Price {stripe_price_id} not found in subscription {stripe_subscription_id} - skipping removal (may have been already removed)"
                )
                return
            else:
                raise ValueError(
                    f"Price {stripe_price_id} not found in subscription {stripe_subscription_id}"
                )

        # 2. Delete the subscription item
        stripe.SubscriptionItem.delete(
            subscription_item_id, proration_behavior=proration_behavior
        )
        logger.info(
            "Successfully removed item from subscription",
            extra={
                "price_id": stripe_price_id,
                "subscription_id": stripe_subscription_id,
            },
        )
    except stripe.StripeError as err:
        logger.error(
            f"Stripe error while removing subscription item: {err}",
            extra={
                "price_id": stripe_price_id,
                "subscription_id": stripe_subscription_id,
            },
        )
        raise
    except ValueError:
        # Re-raise ValueError as-is (from not found check)
        raise
    except Exception as err:
        logger.error(
            f"Unexpected error removing subscription item: {err}",
            extra={
                "price_id": stripe_price_id,
                "subscription_id": stripe_subscription_id,
            },
        )
        raise


def update_subscription_item_price(
    stripe_subscription_id: str,
    old_stripe_price_id: str,
    new_stripe_price_id: str,
    proration_behavior: Literal[
        "always_invoice", "create_prorations", "none"
    ] = "create_prorations",
):
    try:
        subscription = stripe.Subscription.retrieve(stripe_subscription_id)
        subscription_item_id = None

        for item in subscription["items"].data:
            if item and item.price.id == old_stripe_price_id:
                subscription_item_id = item.id
                break

        if not subscription_item_id:
            raise ValueError(
                f"Price {old_stripe_price_id} not found in subscription {stripe_subscription_id}"
            )

        stripe.SubscriptionItem.modify(
            subscription_item_id,
            price=new_stripe_price_id,
            proration_behavior=proration_behavior,
        )

        logger.info(
            "Successfully updated subscription item price",
            extra={
                "old_price_id": old_stripe_price_id,
                "new_price_id": new_stripe_price_id,
                "subscription_id": stripe_subscription_id,
            },
        )
    except Exception as err:
        logger.error(
            f"Failed to update subscription item price due to error: {err}",
            extra={
                "old_price_id": old_stripe_price_id,
                "new_price_id": new_stripe_price_id,
                "subscription_id": stripe_subscription_id,
            },
        )
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
            else:
                logger.warning(
                    "Trial end date is in the past, skipping trial update",
                    extra={"subscription_id": subscription_id},
                )
        # Update payment method if provided
        if payment_method:
            update_params["default_payment_method"] = payment_method

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


def map_stripe_status(stripe_status: str) -> Optional[SubscriptionStatus]:
    """Map a Stripe subscription status string to internal SubscriptionStatus enum."""
    return STRIPE_STATUS_MAP.get(stripe_status)


async def update_subscription_status_from_stripe(
    async_session: AsyncSession,
    stripe_subscription_id: str,
    stripe_status: str,
) -> bool:
    """
    Update subscription status based on Stripe status.
    Handles both account and project subscriptions.

    Args:
        async_session: Async database session
        stripe_subscription_id: The Stripe subscription ID
        stripe_status: The status string from Stripe

    Returns:
        True if status was updated, False otherwise
    """
    # Try account subscription first
    account_sub_repo = AsyncAccountSubscriptionRepository(async_session)
    db_subscription = (
        await account_sub_repo.get_account_subscription_by_stripe_subscription_id(
            stripe_subscription_id
        )
    )

    if db_subscription:
        new_status = map_stripe_status(stripe_status)
        if not new_status:
            logger.warning(f"Unknown Stripe status: {stripe_status}")
            return False

        if db_subscription.status != new_status:
            old_status = (
                db_subscription.status.value if db_subscription.status else "None"
            )
            await account_sub_repo.update_account_subscription_status(
                db_subscription.id, new_status
            )
            logger.info(
                f"Updated account subscription {stripe_subscription_id} status from {old_status} to {new_status.value}"
            )
            return True
        return False

    # Try project subscription
    project_sub_repo = AsyncProjectSubscriptionRepository(async_session)
    project_subscription = await project_sub_repo.get_project_subscription_by_stripe_id(
        stripe_subscription_id
    )

    if not project_subscription:
        logger.warning(
            f"No subscription found for stripe_subscription_id: {stripe_subscription_id}"
        )
        return False

    new_status = map_stripe_status(stripe_status)
    if not new_status:
        logger.warning(f"Unknown Stripe status: {stripe_status}")
        return False

    if project_subscription.status != new_status:
        old_status = (
            project_subscription.status.value if project_subscription.status else "None"
        )
        await project_sub_repo.update_project_subscription_status(
            project_subscription.id, new_status
        )
        logger.info(
            f"Updated project subscription {stripe_subscription_id} status from {old_status} to {new_status.value}"
        )
        return True

    return False


async def handle_subscription_deleted(
    async_session: AsyncSession,
    stripe_subscription_id: str,
    canceled_at: int | None = None,
) -> bool:
    """
    Handle subscription deletion from Stripe.
    Handles both account and project subscriptions.

    Sets status to cancelled and updates end_date if provided.

    Args:
        async_session: Async database session
        stripe_subscription_id: The Stripe subscription ID
        canceled_at: Optional Unix timestamp when subscription was canceled

    Returns:
        True if subscription was updated, False otherwise
    """
    # Try account subscription first
    account_sub_repo = AsyncAccountSubscriptionRepository(async_session)
    db_subscription = (
        await account_sub_repo.get_account_subscription_by_stripe_subscription_id(
            stripe_subscription_id
        )
    )

    if db_subscription:
        await account_sub_repo.update_account_subscription_status(
            db_subscription.id, SubscriptionStatus.cancelled
        )

        if canceled_at and not db_subscription.end_date:
            db_subscription.end_date = datetime.fromtimestamp(
                canceled_at, tz=timezone.utc
            )
            await async_session.flush()

        logger.info(f"Account subscription {stripe_subscription_id} cancelled")
        return True

    # Try project subscription
    project_sub_repo = AsyncProjectSubscriptionRepository(async_session)
    project_subscription = await project_sub_repo.get_project_subscription_by_stripe_id(
        stripe_subscription_id
    )

    if not project_subscription:
        logger.warning(
            f"No subscription found (account or project) for stripe_subscription_id: {stripe_subscription_id}. "
            "This could mean: 1) Subscription was already deleted, 2) Subscription ID mismatch, "
            "3) Test subscription not in database"
        )
        return False

    await project_sub_repo.update_project_subscription_status(
        project_subscription.id, SubscriptionStatus.cancelled
    )

    if canceled_at and not project_subscription.end_date:
        project_subscription.end_date = datetime.fromtimestamp(
            canceled_at, tz=timezone.utc
        )
        await async_session.flush()

    logger.info(f"Project subscription {stripe_subscription_id} cancelled")
    return True


async def sync_subscription_from_stripe(
    async_session: AsyncSession,
    stripe_subscription_id: str,
    stripe_subscription_data: dict[str, Any],
) -> bool:
    """
    Comprehensive sync of subscription data from Stripe webhook.
    Updates status, items (prices), quantities, trial dates, and other fields.
    Handles both account and project subscriptions.

    Args:
        async_session: Async database session
        stripe_subscription_id: The Stripe subscription ID
        stripe_subscription_data: Full subscription object from Stripe webhook

    Returns:
        True if subscription was updated, False otherwise
    """
    stripe_status = stripe_subscription_data.get("status")
    items = stripe_subscription_data.get("items", {}).get("data", [])
    trial_end = stripe_subscription_data.get("trial_end")
    trial_start = stripe_subscription_data.get("trial_start")
    cancel_at = stripe_subscription_data.get("cancel_at")
    canceled_at = stripe_subscription_data.get("canceled_at")
    current_period_end = stripe_subscription_data.get("current_period_end")

    updated = False

    # Try account subscription first
    account_sub_repo = AsyncAccountSubscriptionRepository(async_session)
    db_subscription = (
        await account_sub_repo.get_account_subscription_by_stripe_subscription_id(
            stripe_subscription_id
        )
    )

    if db_subscription:
        # Update status
        if stripe_status:
            new_status = map_stripe_status(stripe_status)
            if new_status and db_subscription.status != new_status:
                old_status = (
                    db_subscription.status.value if db_subscription.status else "None"
                )
                await account_sub_repo.update_account_subscription_status(
                    db_subscription.id, new_status
                )
                logger.info(
                    f"Synced account subscription {stripe_subscription_id} status: {old_status} -> {new_status.value}"
                )
                updated = True

        # Update trial dates
        if trial_start and not db_subscription.trial_start_date:
            db_subscription.trial_start_date = datetime.fromtimestamp(
                trial_start, tz=timezone.utc
            )
            updated = True

        # Update end date if canceled
        timestamp = canceled_at or cancel_at
        if timestamp and not db_subscription.end_date:
            db_subscription.end_date = datetime.fromtimestamp(
                timestamp, tz=timezone.utc
            )
            updated = True

        if updated:
            await async_session.flush()
        return updated

    # Try project subscription
    project_sub_repo = AsyncProjectSubscriptionRepository(async_session)
    project_subscription = await project_sub_repo.get_project_subscription_by_stripe_id(
        stripe_subscription_id
    )

    if not project_subscription:
        logger.warning(
            f"No subscription found for stripe_subscription_id: {stripe_subscription_id}"
        )
        return False

    # Update status
    if stripe_status:
        new_status = map_stripe_status(stripe_status)
        if new_status and project_subscription.status != new_status:
            old_status = (
                project_subscription.status.value
                if project_subscription.status
                else "None"
            )
            await project_sub_repo.update_project_subscription_status(
                project_subscription.id, new_status
            )
            logger.info(
                f"Synced project subscription {stripe_subscription_id} status: {old_status} -> {new_status.value}"
            )
            updated = True

    # Update price IDs from subscription items
    if items:
        for item in items:
            price = item.get("price", {})
            price_id = price.get("id")
            nickname = price.get("nickname", "")

            if not price_id:
                continue

            # Map price nicknames to database fields
            # Nicknames from Stripe: "Base Monthly Fee", "Call Usage", "Order Usage"
            nickname_lower = nickname.lower()

            if (
                "base" in nickname_lower
                and project_subscription.base_price_id != price_id
            ):
                project_subscription.base_price_id = price_id
                updated = True
            elif (
                "call" in nickname_lower
                and project_subscription.call_price_id != price_id
            ):
                project_subscription.call_price_id = price_id
                updated = True
            elif (
                "order" in nickname_lower
                and project_subscription.order_price_id != price_id
            ):
                project_subscription.order_price_id = price_id
                updated = True

    # Update trial dates
    if trial_start and not project_subscription.trial_start_date:
        project_subscription.trial_start_date = datetime.fromtimestamp(
            trial_start, tz=timezone.utc
        )
        updated = True

    # Update start date if not set
    if current_period_end and not project_subscription.start_date:
        # Use trial_end or current_period_start as start_date
        start_timestamp = trial_end or stripe_subscription_data.get(
            "current_period_start"
        )
        if start_timestamp:
            project_subscription.start_date = datetime.fromtimestamp(
                start_timestamp, tz=timezone.utc
            )
            updated = True

    # Update end date if canceled
    timestamp = canceled_at or cancel_at
    if timestamp and not project_subscription.end_date:
        project_subscription.end_date = datetime.fromtimestamp(
            timestamp, tz=timezone.utc
        )
        updated = True

    if updated:
        await async_session.flush()

    return updated


async def sync_account_subscriptions(
    async_session: AsyncSession,
    account_id: uuid.UUID,
) -> dict:
    """
    Sync subscription statuses with Stripe for an account.

    Fetches current status from Stripe and updates local database if out of sync.

    Args:
        async_session: Async database session
        account_id: The account UUID

    Returns:
        Summary dict with synced, updated, errors counts and details
    """
    sub_repo = AsyncAccountSubscriptionRepository(async_session)
    subscriptions = await sub_repo.get_account_subscriptions_with_stripe_id(account_id)

    if not subscriptions:
        return {
            "message": "No subscriptions with Stripe ID found",
            "synced": 0,
            "updated": 0,
            "errors": 0,
            "details": [],
        }

    synced = 0
    updated = 0
    errors = 0
    details: list[dict] = []

    for subscription in subscriptions:
        stripe_sub_id = subscription.stripe_subscription_id
        if not stripe_sub_id:
            continue

        try:
            stripe_sub = stripe.Subscription.retrieve(stripe_sub_id)
            stripe_status = stripe_sub.status

            new_status = map_stripe_status(stripe_status)
            if not new_status:
                logger.warning(
                    f"Unknown Stripe status: {stripe_status} for subscription {stripe_sub_id}"
                )
                errors += 1
                details.append(
                    {
                        "subscription_id": str(subscription.external_id),
                        "stripe_subscription_id": stripe_sub_id,
                        "status": "error",
                        "message": f"Unknown Stripe status: {stripe_status}",
                    }
                )
                continue

            synced += 1

            if subscription.status != new_status:
                old_status = subscription.status.value
                await sub_repo.update_account_subscription_status(
                    subscription.id, new_status
                )
                updated += 1
                details.append(
                    {
                        "subscription_id": str(subscription.external_id),
                        "stripe_subscription_id": stripe_sub_id,
                        "status": "updated",
                        "old_status": old_status,
                        "new_status": new_status.value,
                    }
                )
                logger.debug(
                    "Synced subscription %s: %s -> %s",
                    stripe_sub_id,
                    old_status,
                    new_status.value,
                )
            else:
                details.append(
                    {
                        "subscription_id": str(subscription.external_id),
                        "stripe_subscription_id": stripe_sub_id,
                        "status": "unchanged",
                        "current_status": subscription.status.value,
                    }
                )

        except stripe.StripeError as e:
            logger.error(f"Stripe API error for subscription {stripe_sub_id}: {e}")
            errors += 1
            details.append(
                {
                    "subscription_id": str(subscription.external_id),
                    "stripe_subscription_id": stripe_sub_id,
                    "status": "error",
                    "message": str(e),
                }
            )

    return {
        "message": f"Sync completed: {synced} synced, {updated} updated, {errors} errors",
        "synced": synced,
        "updated": updated,
        "errors": errors,
        "details": details,
    }


def create_subscription_direct(
    stripe_customer_id: str,
    line_items: list[dict[str, Any]],
    metadata: dict[str, str],
    days_until_due: int = 30,
    coupon_id: str | None = None,
    trial_end: int | None = None,
) -> stripe.Subscription:
    """
    Create a Stripe subscription directly via API (no Checkout).

    Uses collection_method="send_invoice" so no payment method is required
    on the customer. Stripe generates invoices that the client pays manually
    via card, ACH, or credits.

    Args:
        stripe_customer_id: Stripe customer ID to create the subscription for
        line_items: List of dicts with 'price' (Stripe price ID) and optional 'quantity'
        metadata: Metadata dict to attach to the subscription
        days_until_due: Number of days the client has to pay each invoice (default 30)
        coupon_id: Optional Stripe coupon ID to apply to the subscription
        trial_end: Optional Unix timestamp for when the trial period ends

    Returns:
        Created Stripe subscription object

    Raises:
        ValueError: If validation fails (empty line_items, invalid params)
        stripe.StripeError: If Stripe API call fails
    """
    if not stripe_customer_id:
        raise ValueError("stripe_customer_id is required")

    if not line_items:
        raise ValueError("line_items cannot be empty")

    for item in line_items:
        if not isinstance(item, dict):
            raise ValueError(f"Invalid line_item format: {item}")
        if "price" not in item:
            raise ValueError(f"Line item must have a 'price' key: {item}")

    if days_until_due < 1:
        raise ValueError("days_until_due must be at least 1")

    # Build subscription items from line_items
    items = []
    for item in line_items:
        sub_item: dict[str, Any] = {"price": item["price"]}
        if "quantity" in item:
            sub_item["quantity"] = item["quantity"]
        items.append(sub_item)

    # Build subscription params
    subscription_params: dict[str, Any] = {
        "customer": stripe_customer_id,
        "items": items,
        "collection_method": "send_invoice",
        "days_until_due": days_until_due,
        "payment_settings": {
            "payment_method_types": ["card", "us_bank_account"],
        },
        "metadata": metadata,
    }

    if coupon_id:
        validate_stripe_coupon(coupon_id)
        subscription_params["coupon"] = coupon_id

    if trial_end is not None:
        subscription_params["trial_end"] = trial_end

    # Require subscription_external_id in metadata — used as the idempotency key
    # to prevent duplicate subscriptions on retries.
    idempotency_key = metadata.get("subscription_external_id")
    if not idempotency_key:
        raise ValueError("metadata must contain 'subscription_external_id'")

    try:
        subscription = stripe.Subscription.create(
            **subscription_params,
            idempotency_key=idempotency_key,
        )

        logger.info(
            "Created Stripe subscription directly (send_invoice)",
            extra={
                "stripe_subscription_id": subscription.id,
                "customer_id": stripe_customer_id,
                "collection_method": "send_invoice",
                "days_until_due": days_until_due,
                "item_count": len(items),
                "has_coupon": coupon_id is not None,
                "has_trial": trial_end is not None,
            },
        )

        return subscription

    except stripe.InvalidRequestError as e:
        error_msg = str(e)
        logger.error(
            "Stripe InvalidRequestError creating direct subscription",
            extra={
                "customer_id": stripe_customer_id,
                "error": error_msg,
            },
        )
        if "No such customer" in error_msg:
            raise ValueError(f"Stripe customer {stripe_customer_id} not found") from e
        if "No such price" in error_msg:
            raise ValueError(f"Invalid price ID in line items: {error_msg}") from e
        raise
    except stripe.StripeError as e:
        logger.error(
            "Stripe error creating direct subscription",
            extra={
                "customer_id": stripe_customer_id,
                "error": str(e),
            },
        )
        raise
