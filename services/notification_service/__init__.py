from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from . import _implementation
from .schema import (
    BillingEvent,
    BillingEventType,
    InvoiceUpcomingPayload,
    PaymentFailedPayload,
    PaymentSucceededPayload,
    SubscriptionActivatedPayload,
    SubscriptionCancelledPayload,
    SubscriptionTrialWillEndPayload,
)


async def handle_billing_event(
    async_session: AsyncSession, event: BillingEvent
) -> None:
    """
    Central handler for all billing events (async version).

    This is the entry point that all billing event sources call.
    In V1, it sends an email synchronously. In V2, it will publish to EventBridge.

    Args:
        async_session: The asynchronous database session
        event: The billing event to handle

    Example:
        >>> event = BillingEvent(
        ...     type=BillingEventType.PAYMENT_SUCCEEDED,
        ...     account_id=UUID("..."),
        ...     payload={"amount_paid": 99.00, "currency": "USD", ...}
        ... )
        >>> await handle_billing_event(async_session, event)
    """
    await _implementation.handle_billing_event(async_session, event)


async def send_billing_email(async_session: AsyncSession, event: BillingEvent) -> None:
    """
    Send billing notification email based on event type (async version).

    Internal function used by handle_billing_event(). Can be called directly
    for testing purposes.

    Args:
        async_session: The asynchronous database session
        event: The billing event to process
    """
    await _implementation.send_billing_email(async_session, event)


def handle_billing_event_sync(session: Session, event: BillingEvent) -> None:
    """
    Central handler for all billing events (sync version).

    This is the sync entry point for sync contexts like subscription service.

    Args:
        session: The synchronous database session
        event: The billing event to handle

    Example:
        >>> event = BillingEvent(
        ...     type=BillingEventType.PAYMENT_SUCCEEDED,
        ...     account_id=UUID("..."),
        ...     payload={"amount_paid": 99.00, "currency": "USD", ...}
        ... )
        >>> handle_billing_event_sync(session, event)
    """
    _implementation.handle_billing_event_sync(session, event)


def send_billing_email_sync(session: Session, event: BillingEvent) -> None:
    """
    Send billing notification email based on event type (sync version).

    Internal function used by handle_billing_event_sync(). Can be called directly
    for testing purposes.

    Args:
        session: The synchronous database session
        event: The billing event to process
    """
    _implementation.send_billing_email_sync(session, event)


__all__ = [
    "handle_billing_event",
    "send_billing_email",
    "handle_billing_event_sync",
    "send_billing_email_sync",
    "BillingEvent",
    "BillingEventType",
    "SubscriptionActivatedPayload",
    "SubscriptionCancelledPayload",
    "SubscriptionTrialWillEndPayload",
    "PaymentFailedPayload",
    "PaymentSucceededPayload",
    "InvoiceUpcomingPayload",
]
