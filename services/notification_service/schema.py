from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class BillingEventType(str, Enum):
    """Types of billing events that trigger notifications."""

    SUBSCRIPTION_ACTIVATED = "subscription_activated"
    SUBSCRIPTION_CANCELLED = "subscription_cancelled"
    PAYMENT_FAILED = "payment_failed"
    PAYMENT_SUCCEEDED = "payment_succeeded"


class BillingEvent(BaseModel):
    """
    Universal billing event model.

    All billing notification triggers must construct this event and call
    handle_billing_event(). The payload is event-specific and flexible.

    Attributes:
        type: The type of billing event
        account_id: The account this event belongs to
        payload: Event-specific data used for email template variables
    """

    type: BillingEventType = Field(..., description="Type of billing event")
    account_id: UUID = Field(..., description="Account ID this event belongs to")
    payload: dict[str, Any] = Field(
        default_factory=dict, description="Event-specific payload for email templates"
    )

    class Config:
        use_enum_values = True


# Event payload type hints for documentation
class SubscriptionActivatedPayload(BaseModel):
    """Payload for SUBSCRIPTION_ACTIVATED events."""

    plan_name: str
    price: float
    currency: str
    trial_end: str | None = None


class SubscriptionCancelledPayload(BaseModel):
    """Payload for SUBSCRIPTION_CANCELLED events."""

    plan_name: str
    cancel_effective_date: str


class PaymentFailedPayload(BaseModel):
    """Payload for PAYMENT_FAILED events."""

    amount_due: float
    currency: str
    attempt_count: int
    invoice_url: str


class PaymentSucceededPayload(BaseModel):
    """Payload for PAYMENT_SUCCEEDED events."""

    amount_paid: float
    currency: str
    invoice_url: str
    period_start: str
    period_end: str
