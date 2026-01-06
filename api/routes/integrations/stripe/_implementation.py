from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import stripe
from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from db.repositories.account_repository import AccountRepositoryAsync
from db.session import AsyncSessionLocal
from services import subscription_service
from services.notification_service import (
    BillingEvent,
    BillingEventType,
    handle_billing_event,
)
from utils.log import logger
from utils.secret import get_server_secret_with_fallback


def _get_stripe_webhook_secret() -> str:
    """
    Get Stripe webhook secret from AWS Secrets Manager with env fallback.

    Returns:
        Stripe webhook signing secret

    Raises:
        ValueError: If secret is not configured
    """
    try:
        return get_server_secret_with_fallback("STRIPE_WEBHOOK_SECRET")
    except ValueError as e:
        logger.error(f"[Stripe Webhook] Failed to retrieve secret: {e}")
        raise


async def _get_account_id_from_stripe_customer(
    async_session: AsyncSession, stripe_customer_id: str
) -> UUID | None:
    """
    Map Stripe customer ID to account ID.

    Args:
        async_session: Database session
        stripe_customer_id: Stripe customer ID

    Returns:
        Account ID (UUID) or None if not found
    """
    account_repo = AccountRepositoryAsync(async_session)
    account = await account_repo.get_account_by_stripe_customer_id(stripe_customer_id)
    if not account:
        logger.warning(
            "[Stripe Webhook] No account found for Stripe customer",
            extra={"stripe_customer_id": stripe_customer_id},
        )
        return None
    return account.id


async def _handle_invoice_payment_failed(
    event_data: dict[str, Any], async_session: AsyncSession
) -> None:
    """
    Handle invoice.payment_failed webhook event.

    Sends a PaymentFailed notification to the account.
    """
    invoice = event_data.get("object", {})
    stripe_customer_id = invoice.get("customer")

    if not stripe_customer_id:
        logger.warning("[Stripe Webhook] invoice.payment_failed missing customer ID")
        return

    account_id = await _get_account_id_from_stripe_customer(
        async_session, stripe_customer_id
    )
    if not account_id:
        return

    billing_event = BillingEvent(
        type=BillingEventType.PAYMENT_FAILED,
        account_id=account_id,
        payload={
            "amount_due": float(invoice.get("amount_due", 0))
            / 100,  # Convert cents to dollars
            "currency": invoice.get("currency", "usd").upper(),
            "attempt_count": invoice.get("attempt_count", 1),
            "invoice_url": invoice.get("hosted_invoice_url", ""),
        },
    )

    await handle_billing_event(async_session, billing_event)

    logger.info(
        "[Stripe Webhook] Processed invoice.payment_failed",
        extra={"account_id": str(account_id)},
    )


async def _handle_invoice_payment_succeeded(
    event_data: dict[str, Any], async_session: AsyncSession
) -> None:
    """
    Handle invoice.payment_succeeded webhook event.

    Sends a PaymentSucceeded notification to the account.
    """
    invoice = event_data.get("object", {})
    stripe_customer_id = invoice.get("customer")

    if not stripe_customer_id:
        logger.warning("[Stripe Webhook] invoice.payment_succeeded missing customer ID")
        return

    account_id = await _get_account_id_from_stripe_customer(
        async_session, stripe_customer_id
    )
    if not account_id:
        return

    period_start = invoice.get("period_start")
    period_end = invoice.get("period_end")

    billing_event = BillingEvent(
        type=BillingEventType.PAYMENT_SUCCEEDED,
        account_id=account_id,
        payload={
            "amount_paid": float(invoice.get("amount_paid", 0))
            / 100,  # Convert cents to dollars
            "currency": invoice.get("currency", "usd").upper(),
            "invoice_url": invoice.get("hosted_invoice_url", ""),
            "period_start": (
                datetime.fromtimestamp(period_start, tz=timezone.utc).strftime(
                    "%B %d, %Y"
                )
                if period_start
                else None
            ),
            "period_end": (
                datetime.fromtimestamp(period_end, tz=timezone.utc).strftime(
                    "%B %d, %Y"
                )
                if period_end
                else None
            ),
        },
    )

    await handle_billing_event(async_session, billing_event)

    logger.info(
        "[Stripe Webhook] Processed invoice.payment_succeeded",
        extra={"account_id": str(account_id)},
    )


async def _handle_invoice_finalized(
    event_data: dict[str, Any], async_session: AsyncSession
) -> None:
    """
    Handle invoice.finalized webhook event.

    Sends an InvoiceSent notification to the account when invoice is finalized.
    This event fires when an invoice is finalized and ready to be sent.
    """
    invoice = event_data.get("object", {})
    stripe_customer_id = invoice.get("customer")

    if not stripe_customer_id:
        logger.warning("[Stripe Webhook] invoice.finalized missing customer ID")
        return

    account_id = await _get_account_id_from_stripe_customer(
        async_session, stripe_customer_id
    )
    if not account_id:
        return

    due_date = invoice.get("due_date")

    billing_event = BillingEvent(
        type=BillingEventType.INVOICE_SENT,
        account_id=account_id,
        payload={
            "invoice_number": invoice.get("number", ""),
            "amount_due": float(invoice.get("amount_due", 0))
            / 100,  # Convert cents to dollars
            "currency": invoice.get("currency", "usd").upper(),
            "due_date": (
                datetime.fromtimestamp(due_date, tz=timezone.utc).strftime("%B %d, %Y")
                if due_date
                else ""
            ),
            "invoice_url": invoice.get("hosted_invoice_url", ""),
            "invoice_pdf": invoice.get("invoice_pdf", ""),
        },
    )

    await handle_billing_event(async_session, billing_event)

    logger.info(
        "[Stripe Webhook] Processed invoice.finalized",
        extra={"account_id": str(account_id)},
    )


# ============================================================================
# Subscription Event Handlers
# ============================================================================


async def _handle_subscription_created(
    event_data: dict[str, Any], async_session: AsyncSession
) -> None:
    """
    Handle customer.subscription.created webhook event.

    Updates the subscription status in the database.
    """
    subscription = event_data.get("object", {})
    stripe_subscription_id = subscription.get("id")
    stripe_customer_id = subscription.get("customer")
    stripe_status = subscription.get("status")

    if not stripe_subscription_id or not stripe_customer_id:
        logger.warning(
            "[Stripe Webhook] customer.subscription.created missing required fields"
        )
        return

    updated = await subscription_service.update_subscription_status_from_stripe(
        async_session, stripe_subscription_id, stripe_status
    )
    if updated:
        logger.info(
            "[Stripe Webhook] Updated subscription status from Stripe",
            extra={
                "stripe_subscription_id": stripe_subscription_id,
                "event": "subscription.created",
            },
        )
    else:
        logger.info(
            "[Stripe Webhook] Subscription created",
            extra={
                "stripe_subscription_id": stripe_subscription_id,
                "stripe_status": stripe_status,
            },
        )


async def _handle_subscription_updated(
    event_data: dict[str, Any], async_session: AsyncSession
) -> None:
    """
    Handle customer.subscription.updated webhook event.

    Syncs the subscription status from Stripe to the database.
    """
    subscription = event_data.get("object", {})
    stripe_subscription_id = subscription.get("id")
    stripe_status = subscription.get("status")

    if not stripe_subscription_id:
        logger.warning(
            "[Stripe Webhook] customer.subscription.updated missing subscription ID"
        )
        return

    updated = await subscription_service.update_subscription_status_from_stripe(
        async_session, stripe_subscription_id, stripe_status
    )
    if updated:
        logger.info(
            "[Stripe Webhook] Updated subscription status from Stripe",
            extra={
                "stripe_subscription_id": stripe_subscription_id,
                "event": "subscription.updated",
            },
        )
    else:
        logger.info(
            "[Stripe Webhook] Subscription updated, status unchanged",
            extra={
                "stripe_subscription_id": stripe_subscription_id,
                "stripe_status": stripe_status,
            },
        )


async def _handle_subscription_deleted(
    event_data: dict[str, Any], async_session: AsyncSession
) -> None:
    """
    Handle customer.subscription.deleted webhook event.

    Sets the subscription status to cancelled and updates end_date.
    """
    subscription = event_data.get("object", {})
    stripe_subscription_id = subscription.get("id")
    canceled_at = subscription.get("canceled_at")

    if not stripe_subscription_id:
        logger.warning(
            "[Stripe Webhook] customer.subscription.deleted missing subscription ID"
        )
        return

    updated = await subscription_service.handle_subscription_deleted(
        async_session, stripe_subscription_id, canceled_at
    )
    if updated:
        logger.info(
            "[Stripe Webhook] Subscription cancelled",
            extra={"stripe_subscription_id": stripe_subscription_id},
        )


# ============================================================================
# Payment Event Handlers (Log Only)
# ============================================================================


async def _handle_payment_intent_succeeded(event_data: dict[str, Any]) -> None:
    """
    Handle payment_intent.succeeded webhook event.

    Logs the payment success for audit trail.
    """
    payment_intent = event_data.get("object", {})
    payment_intent_id = payment_intent.get("id")
    amount = payment_intent.get("amount", 0)
    currency = payment_intent.get("currency", "usd")
    customer_id = payment_intent.get("customer")

    logger.info(
        "[Stripe Webhook] payment_intent.succeeded",
        extra={
            "payment_intent_id": payment_intent_id,
            "amount": amount / 100,
            "currency": currency.upper(),
            "stripe_customer_id": customer_id,
        },
    )


async def _handle_payment_intent_failed(event_data: dict[str, Any]) -> None:
    """
    Handle payment_intent.failed webhook event.

    Logs the payment failure for audit trail.
    """
    payment_intent = event_data.get("object", {})
    payment_intent_id = payment_intent.get("id")
    amount = payment_intent.get("amount", 0)
    currency = payment_intent.get("currency", "usd")
    customer_id = payment_intent.get("customer")
    last_error = payment_intent.get("last_payment_error", {})
    error_message = last_error.get("message", "Unknown error")

    logger.warning(
        "[Stripe Webhook] payment_intent.failed",
        extra={
            "payment_intent_id": payment_intent_id,
            "amount": amount / 100,
            "currency": currency.upper(),
            "stripe_customer_id": customer_id,
            "error": error_message,
        },
    )


async def _handle_charge_succeeded(event_data: dict[str, Any]) -> None:
    """
    Handle charge.succeeded webhook event.

    Logs the charge for audit trail.
    """
    charge = event_data.get("object", {})
    charge_id = charge.get("id")
    amount = charge.get("amount", 0)
    currency = charge.get("currency", "usd")
    customer_id = charge.get("customer")

    logger.info(
        "[Stripe Webhook] charge.succeeded",
        extra={
            "charge_id": charge_id,
            "amount": amount / 100,
            "currency": currency.upper(),
            "stripe_customer_id": customer_id,
        },
    )


async def _handle_charge_failed(event_data: dict[str, Any]) -> None:
    """
    Handle charge.failed webhook event.

    Logs the charge failure with reason.
    """
    charge = event_data.get("object", {})
    charge_id = charge.get("id")
    amount = charge.get("amount", 0)
    currency = charge.get("currency", "usd")
    customer_id = charge.get("customer")
    failure_message = charge.get("failure_message", "Unknown failure")

    logger.warning(
        "[Stripe Webhook] charge.failed",
        extra={
            "charge_id": charge_id,
            "amount": amount / 100,
            "currency": currency.upper(),
            "stripe_customer_id": customer_id,
            "reason": failure_message,
        },
    )


async def _handle_charge_refunded(event_data: dict[str, Any]) -> None:
    """
    Handle charge.refunded webhook event.

    Logs the refund for audit trail.
    """
    charge = event_data.get("object", {})
    charge_id = charge.get("id")
    amount_refunded = charge.get("amount_refunded", 0)
    currency = charge.get("currency", "usd")
    customer_id = charge.get("customer")

    logger.info(
        "[Stripe Webhook] charge.refunded",
        extra={
            "charge_id": charge_id,
            "amount_refunded": amount_refunded / 100,
            "currency": currency.upper(),
            "stripe_customer_id": customer_id,
        },
    )


# ============================================================================
# Customer Event Handlers (Log Only)
# ============================================================================


async def _handle_customer_updated(event_data: dict[str, Any]) -> None:
    """
    Handle customer.updated webhook event.

    Logs customer updates for audit trail.
    """
    customer = event_data.get("object", {})
    customer_id = customer.get("id")
    email = customer.get("email")

    logger.info(
        "[Stripe Webhook] customer.updated",
        extra={"stripe_customer_id": customer_id, "email": email},
    )


async def _handle_customer_deleted(event_data: dict[str, Any]) -> None:
    """
    Handle customer.deleted webhook event.

    Logs customer deletion for audit trail.
    """
    customer = event_data.get("object", {})
    customer_id = customer.get("id")

    logger.warning(
        "[Stripe Webhook] customer.deleted",
        extra={"stripe_customer_id": customer_id},
    )


async def handle_stripe_webhook(request: Request) -> dict[str, str]:
    """
    Handle incoming Stripe webhook events.

    Verifies the webhook signature and processes supported events.
    """
    try:
        # Get raw body for signature verification
        payload = await request.body()

        # Try multiple header name variations (AWS API Gateway may transform headers)
        sig_header = (
            request.headers.get("stripe-signature")
            or request.headers.get("Stripe-Signature")
            or request.headers.get("X-Stripe-Signature")
        )

        # Debug: Log all headers if signature is missing
        if not sig_header:
            logger.warning(
                "[Stripe Webhook] Missing stripe-signature header. Available headers: %s",
                dict(request.headers),
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing stripe-signature header",
            )

        # Verify webhook signature using Stripe SDK
        try:
            webhook_secret = _get_stripe_webhook_secret()
        except ValueError:
            logger.error("[Stripe Webhook] STRIPE_WEBHOOK_SECRET not configured")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Webhook secret not configured",
            )

        try:
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        except ValueError:
            # Invalid payload
            logger.error("[Stripe Webhook] Invalid payload")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid payload",
            )
        except Exception as e:
            # Invalid signature or other Stripe error
            if "signature" in str(e).lower():
                logger.error("[Stripe Webhook] Invalid signature")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid signature",
                )
            # Re-raise other exceptions
            raise

        # Handle specific event types
        event_type = event["type"]
        event_data = event["data"]

        logger.info(
            "[Stripe Webhook] Received event",
            extra={"event_type": event_type},
        )

        # Events that require DB access use a shared session
        async with AsyncSessionLocal() as async_session:
            # Invoice events
            if event_type == "invoice.payment_failed":
                await _handle_invoice_payment_failed(event_data, async_session)
            elif event_type == "invoice.payment_succeeded":
                await _handle_invoice_payment_succeeded(event_data, async_session)
            elif event_type == "invoice.finalized":
                await _handle_invoice_finalized(event_data, async_session)
            # Subscription events
            elif event_type == "customer.subscription.created":
                await _handle_subscription_created(event_data, async_session)
            elif event_type == "customer.subscription.updated":
                await _handle_subscription_updated(event_data, async_session)
            elif event_type == "customer.subscription.deleted":
                await _handle_subscription_deleted(event_data, async_session)
            # Payment events (log only - no DB)
            elif event_type == "payment_intent.succeeded":
                await _handle_payment_intent_succeeded(event_data)
            elif event_type == "payment_intent.failed":
                await _handle_payment_intent_failed(event_data)
            elif event_type == "charge.succeeded":
                await _handle_charge_succeeded(event_data)
            elif event_type == "charge.failed":
                await _handle_charge_failed(event_data)
            elif event_type == "charge.refunded":
                await _handle_charge_refunded(event_data)
            # Customer events (log only - no DB)
            elif event_type == "customer.updated":
                await _handle_customer_updated(event_data)
            elif event_type == "customer.deleted":
                await _handle_customer_deleted(event_data)
            else:
                logger.info(
                    "[Stripe Webhook] Unhandled event type",
                    extra={"event_type": event_type},
                )

            # Single commit for all DB operations in this request
            await async_session.commit()

        return {"status": "success"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "[Stripe Webhook] Error processing webhook",
            extra={"error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing webhook",
        )
