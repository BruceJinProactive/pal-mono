from pydantic import BaseModel


class AdoraWebhookRequest(BaseModel):
    """Request body for Adora webhook"""

    event: str  # e.g. Paid, Ready to pick up, Picked up, Delivered
    PhoneNumber: str
    trackingLink: str | None = None
    storeId: str
    transactionId: str
    orderNumber: str
    orderDate: str


class AdoraWebhookResponse(BaseModel):
    """Response body for Adora webhook"""

    status: str = "succeed"
