from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


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
