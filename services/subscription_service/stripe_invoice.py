import os
from typing import Any
from uuid import UUID

import stripe
from sqlalchemy.orm import Session
from stripe import InvalidRequestError, StripeError

from db.repositories.account_repository import AccountRepository
from db.tables.types import PaymentMethod
from utils.log import logger

# Initialize Stripe API key
STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY")
if STRIPE_API_KEY:
    stripe.api_key = STRIPE_API_KEY
else:
    logger.warning("[Stripe Invoice] STRIPE_API_KEY not configured")

# Invoice payment terms (days until due)
INVOICE_DAYS_UNTIL_DUE = int(os.environ.get("INVOICE_DAYS_UNTIL_DUE", "30"))


def create_manual_invoice(
    stripe_customer_id: str,
    description: str | None = None,
    days_until_due: int | None = None,
) -> Any:
    """
    Create a draft invoice for a customer with manual payment.

    This creates an invoice that includes:
    - All pending invoice items (subscription fees, usage charges)
    - Custom description if provided

    The invoice is created in draft state and must be finalized before sending.

    Args:
        stripe_customer_id: Stripe customer ID
        description: Optional custom description for the invoice
        days_until_due: Days until payment is due (defaults to INVOICE_DAYS_UNTIL_DUE)

    Returns:
        dict: Stripe invoice object

    Raises:
        Exception: If invoice creation fails
    """
    try:
        invoice_params: dict[str, Any] = {
            "customer": stripe_customer_id,
            "auto_advance": False,  # Don't auto-finalize
            "collection_method": "send_invoice",
            "days_until_due": days_until_due or INVOICE_DAYS_UNTIL_DUE,
        }

        if description:
            invoice_params["description"] = description

        invoice = stripe.Invoice.create(**invoice_params)

        logger.info(
            f"[Stripe Invoice] Created draft invoice {invoice.id} for customer {stripe_customer_id}"
        )
        return invoice

    except Exception as e:
        logger.error(
            f"[Stripe Invoice] Failed to create invoice for customer {stripe_customer_id}: {e}"
        )
        raise


def finalize_and_send_invoice(invoice_id: str) -> Any:
    """
    Finalize and send an invoice to the customer.

    Finalizing an invoice:
    - Locks the invoice (no more changes)
    - Calculates final totals
    - Triggers invoice.finalized webhook event

    Sending the invoice:
    - Emails the invoice to the customer
    - Includes payment link
    - Triggers invoice.sent webhook event

    Args:
        invoice_id: Stripe invoice ID

    Returns:
        dict: Updated Stripe invoice object

    Raises:
        ValueError: If invoice not found, already finalized, or operation fails
    """
    try:
        # Finalize the invoice
        stripe.Invoice.finalize_invoice(invoice_id)
        logger.info(f"[Stripe Invoice] Finalized invoice {invoice_id}")

        # Send the invoice via email
        sent_invoice = stripe.Invoice.send_invoice(invoice_id)
        logger.info(f"[Stripe Invoice] Sent invoice {invoice_id} to customer")

        return sent_invoice

    except InvalidRequestError as e:
        logger.error(f"[Stripe Invoice] Invalid request for invoice {invoice_id}: {e}")
        raise ValueError(f"Invalid invoice request: {str(e)}")
    except StripeError as e:
        logger.error(
            f"[Stripe Invoice] Stripe error finalizing/sending invoice {invoice_id}: {e}"
        )
        raise ValueError(f"Failed to finalize/send invoice: {str(e)}")
    except Exception as e:
        logger.error(
            f"[Stripe Invoice] Unexpected error finalizing/sending invoice {invoice_id}: {e}"
        )
        raise ValueError(f"Unexpected error processing invoice: {str(e)}")


def void_invoice(invoice_id: str) -> Any:
    """
    Void an invoice (cancel it).

    Use this to cancel an invoice that was created but should not be paid.

    Args:
        invoice_id: Stripe invoice ID

    Returns:
        dict: Voided Stripe invoice object

    Raises:
        ValueError: If invoice not found, cannot be voided, or operation fails
    """
    try:
        invoice = stripe.Invoice.void_invoice(invoice_id)
        logger.info(f"[Stripe Invoice] Voided invoice {invoice_id}")
        return invoice

    except InvalidRequestError as e:
        logger.error(f"[Stripe Invoice] Invalid request for invoice {invoice_id}: {e}")
        raise ValueError(f"Invalid invoice request: {str(e)}")
    except StripeError as e:
        logger.error(f"[Stripe Invoice] Stripe error voiding invoice {invoice_id}: {e}")
        raise ValueError(f"Failed to void invoice: {str(e)}")
    except Exception as e:
        logger.error(
            f"[Stripe Invoice] Unexpected error voiding invoice {invoice_id}: {e}"
        )
        raise ValueError(f"Unexpected error voiding invoice: {str(e)}")


def get_invoice(invoice_id: str) -> Any:
    """
    Retrieve an invoice by ID.

    Args:
        invoice_id: Stripe invoice ID

    Returns:
        dict: Stripe invoice object

    Raises:
        ValueError: If invoice not found or retrieval fails
    """
    try:
        invoice = stripe.Invoice.retrieve(invoice_id)
        return invoice

    except InvalidRequestError as e:
        logger.error(f"[Stripe Invoice] Invoice not found: {invoice_id}: {e}")
        raise ValueError(f"Invoice not found: {str(e)}")
    except StripeError as e:
        logger.error(
            f"[Stripe Invoice] Stripe error retrieving invoice {invoice_id}: {e}"
        )
        raise ValueError(f"Failed to retrieve invoice: {str(e)}")
    except Exception as e:
        logger.error(
            f"[Stripe Invoice] Unexpected error retrieving invoice {invoice_id}: {e}"
        )
        raise ValueError(f"Unexpected error retrieving invoice: {str(e)}")


def list_customer_invoices(
    stripe_customer_id: str, limit: int = 10, status: str | None = None
) -> list[Any]:
    """
    List invoices for a customer.

    Args:
        stripe_customer_id: Stripe customer ID
        limit: Maximum number of invoices to return
        status: Filter by status (draft, open, paid, void, uncollectible)

    Returns:
        list: List of Stripe invoice objects

    Raises:
        Exception: If listing fails
    """
    try:
        params: dict[str, Any] = {
            "customer": stripe_customer_id,
            "limit": limit,
        }

        if status:
            params["status"] = status

        invoices = stripe.Invoice.list(**params)
        return list(invoices.data)

    except Exception as e:
        logger.error(
            f"[Stripe Invoice] Failed to list invoices for customer {stripe_customer_id}: {e}"
        )
        raise


def get_upcoming_invoice(stripe_customer_id: str) -> Any | None:
    """
    Get the upcoming invoice for a customer (preview).

    This shows what will be charged in the next billing cycle.

    Args:
        stripe_customer_id: Stripe customer ID

    Returns:
        dict | None: Stripe invoice object or None if no upcoming invoice

    Raises:
        Exception: If retrieval fails
    """
    try:
        invoice = stripe.Invoice.upcoming(customer=stripe_customer_id)  # type: ignore[attr-defined]
        return invoice

    except InvalidRequestError as e:
        # No upcoming invoice
        if "Nothing to invoice" in str(e):
            logger.info(
                f"[Stripe Invoice] No upcoming invoice for customer {stripe_customer_id}"
            )
            return None
        raise

    except Exception as e:
        logger.error(
            f"[Stripe Invoice] Failed to get upcoming invoice for customer {stripe_customer_id}: {e}"
        )
        raise


def add_invoice_item(
    stripe_customer_id: str,
    amount: int,
    currency: str,
    description: str,
    invoice_id: str | None = None,
) -> Any:
    """
    Add a custom line item to a customer's next invoice.

    Args:
        stripe_customer_id: Stripe customer ID
        amount: Amount in cents (e.g., 1000 = $10.00)
        currency: Currency code (e.g., 'usd')
        description: Description of the charge
        invoice_id: Optional invoice ID to add item to specific invoice

    Returns:
        dict: Stripe invoice item object

    Raises:
        Exception: If creation fails
    """
    try:
        params: dict[str, Any] = {
            "customer": stripe_customer_id,
            "amount": amount,
            "currency": currency,
            "description": description,
        }

        if invoice_id:
            params["invoice"] = invoice_id

        invoice_item = stripe.InvoiceItem.create(**params)

        logger.info(
            f"[Stripe Invoice] Added invoice item '{description}' ({amount} {currency}) "
            f"for customer {stripe_customer_id}"
        )
        return invoice_item

    except Exception as e:
        logger.error(
            f"[Stripe Invoice] Failed to add invoice item for customer {stripe_customer_id}: {e}"
        )
        raise


def generate_invoice_for_account(
    session: Session,
    account_id: UUID,
    billing_period: str | None = None,
    days_until_due: int | None = None,
) -> Any | None:
    """
    Generate an invoice for an account (if payment_method=invoice).

    This function:
    1. Checks if account uses manual invoicing
    2. Gets the Stripe customer ID
    3. Creates a draft invoice
    4. Finalizes and sends the invoice

    Args:
        session: Database session
        account_id: Account UUID
        billing_period: Optional billing period description (e.g., "March 2025")
        days_until_due: Optional days until due (defaults to INVOICE_DAYS_UNTIL_DUE)

    Returns:
        dict | None: Stripe invoice object or None if account uses autopay

    Raises:
        ValueError: If account not found or missing Stripe customer ID
        Exception: If invoice generation fails
    """
    account_repo = AccountRepository(session)
    account = account_repo.get_account_by_id(account_id)

    if not account:
        raise ValueError(f"Account {account_id} not found")

    # Check if account uses manual invoicing
    # Note: payment_method is on AccountSubscription, need to check active subscription
    if not hasattr(account, "subscriptions") or not account.subscriptions:
        logger.warning(f"[Stripe Invoice] Account {account.name} has no subscriptions")
        return None

    # Get active subscription
    active_subscription = next(
        (sub for sub in account.subscriptions if sub.is_valid), None
    )

    if not active_subscription:
        logger.warning(
            f"[Stripe Invoice] Account {account.name} has no active subscription"
        )
        return None

    if active_subscription.payment_method != PaymentMethod.invoice:
        logger.info(
            f"[Stripe Invoice] Account {account.name} uses autopay, skipping invoice generation"
        )
        return None

    if not account.stripe_customer_id:
        raise ValueError(
            f"Account {account.name} has invoice payment method but no Stripe customer ID"
        )

    # Create description
    description = f"Invoice for {account.name}"
    if billing_period:
        description += f" - {billing_period}"

    # Create and send invoice
    invoice = create_manual_invoice(
        stripe_customer_id=account.stripe_customer_id,
        description=description,
        days_until_due=days_until_due,
    )

    finalized_invoice = finalize_and_send_invoice(invoice.id)

    logger.info(
        f"[Stripe Invoice] Generated invoice {finalized_invoice.id} for account {account.name}"
    )

    return finalized_invoice
