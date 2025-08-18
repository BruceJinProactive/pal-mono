from pydantic import BaseModel


class ToastWebhookRequest(BaseModel):
    """Request body for Toast webhook"""

    timestamp: str
    eventCategory: str
    eventType: str
    guid: str
    details: dict


class ToastWebhookResponse(BaseModel):
    """Response body for Toast webhook"""

    message: str = "Success"
