import os
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import stripe
from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from db.repositories.account_repository import AccountRepositoryAsync
from db.session import AsyncSessionLocal
from services.notification_service import (
    BillingEvent,
    BillingEventType,
    handle_billing_event,
)
from utils.log import logger

# Stripe webhook signing secret from environment
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")
if not STRIPE_WEBHOOK_SECRET:
    logger.warning(
        "[Stripe Webhook] STRIPE_WEBHOOK_SECRET not configured - webhooks will fail"
    )


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
            f"[Stripe Webhook] No account found for Stripe customer {stripe_customer_id}"
        )
        return None
    return account.id


async def _handle_invoice_payment_failed(event_data: dict[str, Any]) -> None:
    """
    Handle invoice.payment_failed webhook event.

    Sends a PaymentFailed notification to the account.
    """
    invoice = event_data.get("object", {})
    stripe_customer_id = invoice.get("customer")

    if not stripe_customer_id:
        logger.warning("[Stripe Webhook] invoice.payment_failed missing customer ID")
        return

    async with AsyncSessionLocal() as async_session:
        account_id = await _get_account_id_from_stripe_customer(
            async_session, stripe_customer_id
        )
        if not account_id:
            return

        # Build event payload
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
        f"[Stripe Webhook] Processed invoice.payment_failed for account {account_id}"
    )


async def _handle_invoice_payment_succeeded(event_data: dict[str, Any]) -> None:
    """
    Handle invoice.payment_succeeded webhook event.

    Sends a PaymentSucceeded notification to the account.
    """
    invoice = event_data.get("object", {})
    stripe_customer_id = invoice.get("customer")

    if not stripe_customer_id:
        logger.warning("[Stripe Webhook] invoice.payment_succeeded missing customer ID")
        return

    async with AsyncSessionLocal() as async_session:
        account_id = await _get_account_id_from_stripe_customer(
            async_session, stripe_customer_id
        )
        if not account_id:
            return

        # Build event payload
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
        f"[Stripe Webhook] Processed invoice.payment_succeeded for account {account_id}"
    )


async def _handle_invoice_finalized(event_data: dict[str, Any]) -> None:
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

    async with AsyncSessionLocal() as async_session:
        account_id = await _get_account_id_from_stripe_customer(
            async_session, stripe_customer_id
        )
        if not account_id:
            return

        # Build event payload
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
                    datetime.fromtimestamp(due_date, tz=timezone.utc).strftime(
                        "%B %d, %Y"
                    )
                    if due_date
                    else ""
                ),
                "invoice_url": invoice.get("hosted_invoice_url", ""),
                "invoice_pdf": invoice.get("invoice_pdf", ""),
            },
        )

        await handle_billing_event(async_session, billing_event)

    logger.info(
        f"[Stripe Webhook] Processed invoice.finalized for account {account_id}"
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
            event = stripe.Webhook.construct_event(
                payload, sig_header, STRIPE_WEBHOOK_SECRET
            )
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

        logger.info(f"[Stripe Webhook] Received event: {event_type}")

        if event_type == "invoice.payment_failed":
            await _handle_invoice_payment_failed(event_data)
        elif event_type == "invoice.payment_succeeded":
            await _handle_invoice_payment_succeeded(event_data)
        elif event_type == "invoice.finalized":
            await _handle_invoice_finalized(event_data)
        else:
            logger.info(f"[Stripe Webhook] Unhandled event type: {event_type}")

        return {"status": "success"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Stripe Webhook] Error processing webhook: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing webhook",
        )
