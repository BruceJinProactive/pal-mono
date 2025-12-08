from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from db.repositories.account_repository import AccountRepository, AccountRepositoryAsync
from services.email_service import send_email_with_template
from utils.log import logger

from .schema import BillingEvent, BillingEventType

# Postmark template IDs for each billing event type
POSTMARK_TEMPLATES = {
    BillingEventType.SUBSCRIPTION_ACTIVATED: 42419409,
    BillingEventType.SUBSCRIPTION_CANCELLED: 42419436,
    BillingEventType.PAYMENT_FAILED: 42419416,
    BillingEventType.PAYMENT_SUCCEEDED: 42419437,
}


def _format_currency_amount(amount: float, currency: str) -> str:
    """
    Format currency amount for email display.

    Args:
        amount: Amount in the currency's base unit (e.g., dollars, not cents)
        currency: Currency code (USD, EUR, etc.)

    Returns:
        Formatted string (e.g., "$99.99")
    """
    currency_symbols = {
        "USD": "$",
        "EUR": "€",
        "GBP": "£",
    }
    symbol = currency_symbols.get(currency.upper(), currency.upper() + " ")
    return f"{symbol}{amount:.2f}"


def _build_template_variables(event: BillingEvent, account_name: str) -> dict[str, str]:
    """
    Map billing event payload to Postmark template variables.

    Args:
        event: The billing event
        account_name: Name of the account for personalization

    Returns:
        Dictionary of template variables for Postmark
    """
    # Base variables available in all emails
    variables = {
        "account_name": account_name,
        "billing_url": "https://console.palona.ai/settings/subscription",
    }

    payload = event.payload

    # Event-specific template variables
    if event.type == BillingEventType.SUBSCRIPTION_ACTIVATED:
        variables.update(
            {
                "plan_name": payload.get("plan_name", "Unknown Plan"),
                "price_formatted": _format_currency_amount(
                    payload.get("price", 0), payload.get("currency", "USD")
                ),
                "trial_end": payload.get("trial_end", ""),
            }
        )

    elif event.type == BillingEventType.SUBSCRIPTION_CANCELLED:
        variables.update(
            {
                "plan_name": payload.get("plan_name", "Unknown Plan"),
                "cancel_effective_date": payload.get("cancel_effective_date", ""),
            }
        )

    elif event.type == BillingEventType.PAYMENT_FAILED:
        variables.update(
            {
                "amount_due_formatted": _format_currency_amount(
                    payload.get("amount_due", 0), payload.get("currency", "USD")
                ),
                "attempt_count": str(payload.get("attempt_count", 1)),
                "invoice_url": payload.get("invoice_url", ""),
            }
        )

    elif event.type == BillingEventType.PAYMENT_SUCCEEDED:
        variables.update(
            {
                "amount_paid_formatted": _format_currency_amount(
                    payload.get("amount_paid", 0), payload.get("currency", "USD")
                ),
                "invoice_url": payload.get("invoice_url", ""),
                "period_start": payload.get("period_start", ""),
                "period_end": payload.get("period_end", ""),
            }
        )

    return variables


async def send_billing_email(async_session: AsyncSession, event: BillingEvent) -> None:
    """
    Send billing notification email based on event type.

    This is the core email sending logic for V1. It:
    1. Loads the account
    2. Checks notification preferences
    3. Resolves recipient email
    4. Maps event to Postmark template
    5. Sends email via Postmark

    Args:
        event: The billing event to process

    Raises:
        No exceptions are raised. Errors are logged and gracefully handled.
    """
    try:
        # 1. Load account
        account_repository = AccountRepositoryAsync(async_session)
        account = await account_repository.get_account_by_id(event.account_id)
        if not account:
            logger.warning(
                "[send_billing_email] Account not found for billing event",
                extra={
                    "account_id": str(event.account_id),
                    "event_type": event.type,
                },
            )
            return

        # 2. Check notification preferences
        prefs = account.notification_preferences or {}
        email_enabled = prefs.get("email_enabled", True)
        if not email_enabled:
            logger.info(
                "[send_billing_email] Email notifications disabled for account",
                extra={
                    "account_id": str(event.account_id),
                    "event_type": event.type,
                },
            )
            return

        # 3. Resolve recipient email
        recipient = account.notification_email
        if not recipient:
            logger.warning(
                "[send_billing_email] No recipient email for account",
                extra={
                    "account_id": str(event.account_id),
                    "event_type": event.type,
                },
            )
            return

        # 4. Build template variables
        template_variables = _build_template_variables(event, account.name)

        # 5. Send email via Postmark
        logger.info(
            "[send_billing_email] Sending billing notification",
            extra={
                "account_id": str(event.account_id),
                "event_type": event.type,
                "recipient": recipient,
            },
        )

        send_email_with_template(
            to_email=recipient,
            template_id=POSTMARK_TEMPLATES[event.type],
            template_model=template_variables,
            tag=f"billing-{event.type}",
        )

        logger.info(
            "[send_billing_email] Billing notification sent successfully",
            extra={
                "account_id": str(event.account_id),
                "event_type": event.type,
            },
        )

    except Exception:
        # Log error but don't raise
        logger.warning(
            "[send_billing_email] Failed to send billing notification",
            extra={"account_id": str(event.account_id), "event_type": event.type},
            exc_info=True,
        )


async def handle_billing_event(
    async_session: AsyncSession, event: BillingEvent
) -> None:
    """
    Central handler for all billing events.

    This is the entry point that all billing event sources call.
    It simply delegates to send_billing_email().

    Args:
        async_session: The asynchronous database session
        event: The billing event to handle

    Example:
        >>> from services.notification_service import BillingEvent, BillingEventType, handle_billing_event
        >>> event = BillingEvent(
        ...     type=BillingEventType.PAYMENT_SUCCEEDED,
        ...     account_id=UUID("..."),
        ...     payload={"amount_paid": 99.00, "currency": "USD", ...}
        ... )
        >>> await handle_billing_event(async_session, event)
    """
    logger.info(
        "[handle_billing_event] Processing billing event",
        extra={
            "account_id": str(event.account_id),
            "event_type": event.type,
        },
    )

    await send_billing_email(async_session, event)


def send_billing_email_sync(session: Session, event: BillingEvent) -> None:
    """
    Send billing notification email based on event type (sync version).

    This is a synchronous version for use from sync contexts like subscription service.

    Args:
        session: The synchronous database session
        event: The billing event to process

    Raises:
        No exceptions are raised. Errors are logged and gracefully handled.
    """
    try:
        # 1. Load account
        account_repository = AccountRepository(session)
        account = account_repository.get_account_by_id(event.account_id)
        if not account:
            logger.warning(
                "[send_billing_email_sync] Account not found for billing event",
                extra={
                    "account_id": str(event.account_id),
                    "event_type": event.type,
                },
            )
            return

        # 2. Check notification preferences
        prefs = account.notification_preferences or {}
        email_enabled = prefs.get("email_enabled", True)
        if not email_enabled:
            logger.info(
                "[send_billing_email_sync] Email notifications disabled for account",
                extra={
                    "account_id": str(event.account_id),
                    "event_type": event.type,
                },
            )
            return

        # 3. Resolve recipient email
        recipient = account.notification_email
        if not recipient:
            logger.warning(
                "[send_billing_email_sync] No recipient email for account",
                extra={
                    "account_id": str(event.account_id),
                    "event_type": event.type,
                },
            )
            return

        # 4. Build template variables
        template_variables = _build_template_variables(event, account.name)

        # 5. Send email via Postmark
        logger.info(
            "[send_billing_email_sync] Sending billing notification",
            extra={
                "account_id": str(event.account_id),
                "event_type": event.type,
                "recipient": recipient,
            },
        )

        send_email_with_template(
            to_email=recipient,
            template_id=POSTMARK_TEMPLATES[event.type],
            template_model=template_variables,
            tag=f"billing-{event.type}",
        )

        logger.info(
            "[send_billing_email_sync] Billing notification sent successfully",
            extra={
                "account_id": str(event.account_id),
                "event_type": event.type,
            },
        )

    except Exception:
        # Log error but don't raise
        logger.warning(
            "[send_billing_email_sync] Failed to send billing notification",
            extra={"account_id": str(event.account_id), "event_type": event.type},
            exc_info=True,
        )


def handle_billing_event_sync(session: Session, event: BillingEvent) -> None:
    """
    Central handler for all billing events (sync version).

    This is the sync entry point for sync contexts like subscription service.

    Args:
        session: The synchronous database session
        event: The billing event to handle

    Example:
        >>> from services.notification_service import BillingEvent, BillingEventType, handle_billing_event_sync
        >>> event = BillingEvent(
        ...     type=BillingEventType.PAYMENT_SUCCEEDED,
        ...     account_id=UUID("..."),
        ...     payload={"amount_paid": 99.00, "currency": "USD", ...}
        ... )
        >>> handle_billing_event_sync(session, event)
    """
    logger.info(
        "[handle_billing_event_sync] Processing billing event",
        extra={
            "account_id": str(event.account_id),
            "event_type": event.type,
        },
    )

    send_billing_email_sync(session, event)
