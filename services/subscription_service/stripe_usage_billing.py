import os
from datetime import UTC, datetime
from typing import Optional

import stripe

from utils.log import logger

stripe.api_key = os.environ.get("STRIPE_API_KEY")
try:
    from stripe import StripeClient
except Exception:
    StripeClient = None


class StripeUsageBillingService:
    """Service for managing Stripe products and prices for usage billing."""

    CALLS_METER_EVENT_NAME = "pal_calls"
    CALLS_METER_DISPLAY_NAME = "PAL Calls"
    ORDERS_METER_EVENT_NAME = "pal_orders"
    ORDERS_METER_DISPLAY_NAME = "PAL Orders"

    @staticmethod
    def _get_stripe_client() -> Optional[StripeClient]:  # type: ignore[valid-type]
        api_key = os.environ.get("STRIPE_API_KEY")
        if StripeClient and api_key:
            try:
                return StripeClient(api_key)
            except Exception:
                return None
        return None

    @staticmethod
    def send_meter_event(
        event_name: str,
        stripe_customer_id: str,
        value: int = 1,
        timestamp: Optional[datetime] = None,
    ) -> bool:
        """
        Send a meter event to Stripe for usage tracking.

        Args:
            event_name: The meter event name (e.g., 'pal_calls', 'pal_orders')
            stripe_customer_id: The Stripe customer ID for billing
            value: The usage value (default 1 for single call/order)
            timestamp: Event timestamp (defaults to current time)

        Returns:
            bool: True if event was sent successfully, False otherwise
        """
        try:
            client = StripeUsageBillingService._get_stripe_client()
            if not client:
                logger.error("StripeClient unavailable; cannot send meter event")
                return False

            event_timestamp = timestamp or datetime.now(UTC)

            # Try modern client first
            try:
                client.billing.meter_events.create(
                    {
                        "event_name": event_name,
                        "payload": {
                            "stripe_customer_id": stripe_customer_id,
                            "value": str(value),
                        },
                        "timestamp": int(event_timestamp.timestamp()),
                    }
                )
                return True
            except Exception as e:
                logger.warning(
                    f"Modern client meter event failed, trying raw_request: {e}"
                )
                # Fallback to raw request
                response = client.raw_request(
                    "post",
                    "/v1/billing/meter_events",
                    event_name=event_name,
                    payload={
                        "stripe_customer_id": stripe_customer_id,
                        "value": str(value),
                    },
                    timestamp=int(event_timestamp.timestamp()),
                )
                deserialized = client.deserialize(response, api_mode="V1")
                return bool(getattr(deserialized, "id", None))

        except Exception as e:
            logger.error(
                f"Failed to send meter event: {e}",
                extra={
                    "event_name": event_name,
                    "stripe_customer_id": stripe_customer_id,
                    "value": value,
                },
            )
            return False
