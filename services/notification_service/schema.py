from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class BillingEventType(str, Enum):
    """Types of billing events that trigger notifications."""

    SUBSCRIPTION_ACTIVATED = "subscription_activated"
    SUBSCRIPTION_CANCELLED = "subscription_cancelled"
    SUBSCRIPTION_TRIAL_WILL_END = "subscription_trial_will_end"
    PAYMENT_FAILED = "payment_failed"
    PAYMENT_SUCCEEDED = "payment_succeeded"
    INVOICE_SENT = "invoice_sent"
    INVOICE_UPCOMING = "invoice_upcoming"
    INVOICE_PAYMENT_DUE_SOON = "invoice_payment_due_soon"
    INVOICE_OVERDUE = "invoice_overdue"


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


class InvoiceSentPayload(BaseModel):
    """Payload for INVOICE_SENT events."""

    invoice_number: str
    amount_due: float
    currency: str
    due_date: str
    invoice_url: str
    invoice_pdf: str


class InvoicePaymentDueSoonPayload(BaseModel):
    """Payload for INVOICE_PAYMENT_DUE_SOON events."""

    invoice_number: str
    amount_due: float
    currency: str
    due_date: str
    days_until_due: int
    invoice_url: str


class InvoiceOverduePayload(BaseModel):
    """Payload for INVOICE_OVERDUE events."""

    invoice_number: str
    amount_due: float
    currency: str
    due_date: str
    days_overdue: int
    invoice_url: str


class SubscriptionTrialWillEndPayload(BaseModel):
    """Payload for SUBSCRIPTION_TRIAL_WILL_END events."""

    plan_name: str
    trial_end_date: str
    days_until_trial_end: int


class InvoiceUpcomingPayload(BaseModel):
    """Payload for INVOICE_UPCOMING events."""

    amount_due: float
    currency: str
    next_payment_date: str
    period_start: str
    period_end: str
