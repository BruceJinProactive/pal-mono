from datetime import UTC, datetime
from typing import Optional

import stripe

from utils.log import logger


def send_meter_event(
    event_name: str,
    stripe_customer_id: str,
    value: int = 1,
    timestamp: Optional[datetime] = None,
) -> bool:
    """
    Send a meter event to Stripe for usage tracking.

    Args:
        event_name: The meter event name (e.g., 'calls_project_id', 'orders_project_id')
        stripe_customer_id: The Stripe customer ID for billing
        value: The usage value (default 1 for single call/order)
        timestamp: Event timestamp (defaults to current time)

    Returns:
        bool: True if event was sent successfully, False otherwise
    """
    try:
        event_timestamp = timestamp or datetime.now(UTC)

        stripe.billing.MeterEvent.create(
            event_name=event_name,
            payload={
                "stripe_customer_id": stripe_customer_id,
                "value": str(value),
            },
            timestamp=int(event_timestamp.timestamp()),
        )
        return True

    except Exception as e:
        error_message = str(e)
        if "No active meter found" in error_message:
            # This is expected when project doesn't have an active subscription
            # Log at info level instead of warning to reduce noise
            logger.info(
                "No active meter configured for event - skipping usage tracking",
                extra={
                    "event_name": event_name,
                    "stripe_customer_id": stripe_customer_id,
                    "value": value,
                },
            )
        else:
            logger.error(
                f"Failed to send meter event: {e}",
                extra={
                    "event_name": event_name,
                    "stripe_customer_id": stripe_customer_id,
                    "value": value,
                },
            )
        return False
