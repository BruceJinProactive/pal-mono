from uuid import UUID

from sqlalchemy.orm import Session

from db.repositories.account_repository import AccountRepository
from db.repositories.subscription_repository import AccountSubscriptionRepository
from db.tables.types import PaymentMethod
from services.subscription_service.stripe_invoice import (
    finalize_and_send_invoice,
    generate_invoice_for_account,
    get_invoice,
    list_customer_invoices,
    void_invoice,
)
from utils.log import logger


def update_payment_method(
    session: Session, account_id: UUID, payment_method: str
) -> dict[str, str]:
    """
    Update the payment method for an account's subscription.

    Args:
        session: Database session
        account_id: Account UUID
        payment_method: 'autopay' or 'invoice'

    Returns:
        dict: Account and payment method info

    Raises:
        ValueError: If account or subscription not found, or invalid payment method
    """
    # Validate payment method
    try:
        payment_method_enum = PaymentMethod(payment_method)
    except ValueError:
        raise ValueError(
            f"Invalid payment method: {payment_method}. Must be 'autopay' or 'invoice'"
        )

    # Get account
    account_repo = AccountRepository(session)
    account = account_repo.get_account_by_id(account_id)

    if not account:
        raise ValueError(f"Account {account_id} not found")

    # Get active subscription
    subscription_repo = AccountSubscriptionRepository(session)
    active_subscription = subscription_repo.get_active_account_subscription(account_id)

    if not active_subscription:
        raise ValueError(f"No active subscription found for account {account.name}")

    # Update payment method
    old_payment_method = active_subscription.payment_method
    subscription_repo.update_payment_method(active_subscription.id, payment_method_enum)

    logger.info(
        f"[Billing Service] Updated payment method for account {account.name} "
        f"from {old_payment_method.value} to {payment_method}"
    )

    return {
        "account_id": str(account_id),
        "account_name": account.name,
        "old_payment_method": old_payment_method.value,
        "new_payment_method": payment_method,
    }


def generate_manual_invoice(
    session: Session,
    account_id: UUID,
    billing_period: str | None = None,
    days_until_due: int | None = None,
) -> dict:
    """
    Manually generate and send an invoice for an account.

    This can be used for:
    - Generating invoices on-demand
    - Creating invoices outside normal billing cycle
    - Testing invoice generation

    Args:
        session: Database session
        account_id: Account UUID
        billing_period: Optional billing period description
        days_until_due: Optional days until due (defaults to 30)

    Returns:
        dict: Generated invoice details

    Raises:
        ValueError: If account not found or doesn't use invoice payment
    """
    invoice = generate_invoice_for_account(
        session=session,
        account_id=account_id,
        billing_period=billing_period,
        days_until_due=days_until_due,
    )

    if not invoice:
        raise ValueError(
            "Account does not use invoice payment method or invoice generation failed"
        )

    return {
        "invoice_id": invoice.id,
        "invoice_number": invoice.number,
        "status": invoice.status,
        "amount_due": float(invoice.amount_due) / 100,
        "currency": invoice.currency.upper(),
        "due_date": invoice.due_date,
        "invoice_url": invoice.hosted_invoice_url,
        "invoice_pdf": invoice.invoice_pdf,
    }


def get_account_invoices(
    session: Session, account_id: UUID, limit: int = 10, status: str | None = None
) -> list[dict]:
    """
    Get invoices for an account.

    Args:
        session: Database session
        account_id: Account UUID
        limit: Maximum number of invoices to return
        status: Filter by status (draft, open, paid, void, uncollectible)

    Returns:
        list: List of invoice details

    Raises:
        ValueError: If account not found or missing Stripe customer ID
    """
    account_repo = AccountRepository(session)
    account = account_repo.get_account_by_id(account_id)

    if not account:
        raise ValueError(f"Account {account_id} not found")

    if not account.stripe_customer_id:
        raise ValueError(f"Account {account.name} has no Stripe customer ID")

    invoices = list_customer_invoices(
        stripe_customer_id=account.stripe_customer_id,
        limit=limit,
        status=status,
    )

    return [
        {
            "invoice_id": inv.id,
            "invoice_number": inv.number,
            "status": inv.status,
            "amount_due": float(inv.amount_due) / 100,
            "currency": inv.currency.upper(),
            "due_date": inv.due_date,
            "invoice_url": inv.hosted_invoice_url,
            "invoice_pdf": inv.invoice_pdf,
            "line_items": [
                {
                    "description": item.description,
                    "amount": float(item.amount) / 100,
                    "currency": item.currency.upper(),
                }
                for item in (inv.lines.data if hasattr(inv.lines, "data") else [])
            ],
        }
        for inv in invoices
    ]


def finalize_invoice(session: Session, account_id: UUID, invoice_id: str) -> dict:
    """
    Finalize and send a draft invoice.

    Args:
        session: Database session
        account_id: Account UUID (for authorization)
        invoice_id: Stripe invoice ID

    Returns:
        dict: Finalized invoice details

    Raises:
        ValueError: If account not found or not authorized
    """
    # Verify account exists and owns this invoice
    invoice = get_invoice(invoice_id)
    account_repo = AccountRepository(session)
    account = account_repo.get_account_by_id(account_id)

    if not account:
        raise ValueError(f"Account {account_id} not found")

    if invoice.customer != account.stripe_customer_id:
        raise ValueError("Account does not own this invoice")

    # Finalize and send
    finalized = finalize_and_send_invoice(invoice_id)

    return {
        "invoice_id": finalized.id,
        "status": finalized.status,
        "message": "Invoice finalized and sent to customer",
    }


def cancel_invoice(session: Session, account_id: UUID, invoice_id: str) -> dict:
    """
    Cancel (void) an invoice.

    Args:
        session: Database session
        account_id: Account UUID (for authorization)
        invoice_id: Stripe invoice ID

    Returns:
        dict: Cancelled invoice details

    Raises:
        ValueError: If account not found or not authorized
    """
    # Verify account exists and owns this invoice
    invoice = get_invoice(invoice_id)
    account_repo = AccountRepository(session)
    account = account_repo.get_account_by_id(account_id)

    if not account:
        raise ValueError(f"Account {account_id} not found")

    if invoice.customer != account.stripe_customer_id:
        raise ValueError("Account does not own this invoice")

    # Void the invoice
    voided = void_invoice(invoice_id)

    return {
        "invoice_id": voided.id,
        "status": voided.status,
        "message": "Invoice cancelled successfully",
    }
