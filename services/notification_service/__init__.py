from sqlalchemy.ext.asyncio import AsyncSession

from . import _implementation
from .schema import (
    BillingEvent,
    BillingEventType,
    PaymentFailedPayload,
    PaymentSucceededPayload,
    SubscriptionActivatedPayload,
    SubscriptionCancelledPayload,
)


async def handle_billing_event(
    async_session: AsyncSession, event: BillingEvent
) -> None:
    """
    Central handler for all billing events.

    This is the entry point that all billing event sources call.
    In V1, it sends an email synchronously. In V2, it will publish to EventBridge.

    Args:
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
    Send billing notification email based on event type.

    Internal function used by handle_billing_event(). Can be called directly
    for testing purposes.

    Args:
        event: The billing event to process
    """
    await _implementation.send_billing_email(async_session, event)


__all__ = [
    "handle_billing_event",
    "send_billing_email",
    "BillingEvent",
    "BillingEventType",
    "SubscriptionActivatedPayload",
    "SubscriptionCancelledPayload",
    "PaymentFailedPayload",
    "PaymentSucceededPayload",
]
