from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class UpdatePaymentMethodRequest(BaseModel):
    """Request to update account payment method."""

    payment_method: str = Field(
        ...,
        description="Payment method: 'autopay' or 'invoice'",
        pattern="^(autopay|invoice)$",
    )


class UpdatePaymentMethodResponse(BaseModel):
    """Response after updating payment method."""

    account_id: UUID
    account_name: str
    payment_method: str
    message: str


class GenerateInvoiceRequest(BaseModel):
    """Request to manually generate an invoice."""

    billing_period: Optional[str] = Field(
        None, description="Optional billing period description (e.g., 'March 2025')"
    )
    days_until_due: Optional[int] = Field(
        30, description="Days until payment is due (default: 30)"
    )


class InvoiceLineItem(BaseModel):
    """Invoice line item."""

    description: str
    amount: float
    currency: str


class InvoiceResponse(BaseModel):
    """Invoice details response."""

    invoice_id: str
    invoice_number: Optional[str] = None
    status: str
    amount_due: float
    currency: str
    due_date: Optional[datetime] = None
    invoice_url: Optional[str] = None
    invoice_pdf: Optional[str] = None
    line_items: List[InvoiceLineItem] = Field(default_factory=list)


class GenerateInvoiceResponse(BaseModel):
    """Response after generating an invoice."""

    invoice: InvoiceResponse
    message: str


class ListInvoicesResponse(BaseModel):
    """List of invoices for an account."""

    invoices: List[InvoiceResponse]
    total_count: int


class InvoiceActionRequest(BaseModel):
    """Request to perform an action on an invoice."""

    invoice_id: str = Field(..., description="Stripe invoice ID")


class InvoiceActionResponse(BaseModel):
    """Response after performing an invoice action."""

    invoice_id: str
    status: str
    message: str


class SendInvoiceEmailRequest(BaseModel):
    """Request to send an invoice email with analytics and PDF attachment.

    Either pdf_base64 or stripe_invoice_id must be provided.
    If stripe_invoice_id is provided, the PDF will be fetched from Stripe automatically.
    """

    to_email: EmailStr
    period_start: str  # e.g., "December 1"
    period_end: str  # e.g., "December 31, 2025"
    calls_handled: int
    total_minutes: int
    staff_hours_saved: int
    total_orders: int = Field(0, description="Total paid orders in billing period")
    order_total_dollars: float = Field(
        0.0, description="Total dollar value of paid orders"
    )
    total_reservations: int = Field(
        0, description="Total reservations booked in billing period"
    )
    pdf_base64: Optional[str] = None  # Base64 encoded PDF content (manual upload)
    stripe_invoice_id: Optional[str] = (
        None  # Stripe invoice ID (auto-fetch from Stripe)
    )
    pdf_filename: Optional[str] = None  # e.g., "invoice_december_2025.pdf"
    cc_emails: Optional[list[EmailStr]] = None
    template_id: int | None = Field(
        None,
        gt=0,
        description="Postmark template ID (from /billing/metrics). Uses default if not provided.",
    )


class SendInvoiceEmailResponse(BaseModel):
    """Response after sending an invoice email."""

    success: bool
    message: str
    message_id: Optional[str] = None


class BillingMetricsResponse(BaseModel):
    """Response containing billing metrics for an account over a date range."""

    account_name: str = Field(..., description="Account identifier")
    period_start: str = Field(..., description="Start of billing period (ISO date)")
    period_end: str = Field(..., description="End of billing period (ISO date)")
    total_calls: int = Field(..., description="Total number of calls handled")
    avg_call_duration_seconds: float = Field(
        ..., description="Average call duration in seconds"
    )
    total_reservations: int = Field(..., description="Total reservations booked")
    total_orders: int = Field(..., description="Total orders placed (paid)")
    order_total_dollars: float = Field(
        ..., description="Total dollar value of paid orders"
    )
    template_variant: str = Field(
        ..., description="Suggested invoice template variant based on activity"
    )
    template_id: int = Field(
        ..., description="Postmark template ID for the invoice email"
    )
