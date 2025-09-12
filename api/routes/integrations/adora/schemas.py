from typing import Optional

from pydantic import BaseModel, Field


class AdoraWebhookRequest(BaseModel):
    """Request body for Adora webhook

    Required parameters by event:

    For order status events (e.g., 'Paid', 'Ready to pick up', 'Delivered'):
    - event, storeId, PhoneNumber, transactionId, orderNumber, orderDate
    - trackingLink (optional)

    For menu update events ('update_menu'):
    - event, storeId, brandId
    """

    # Required fields
    event: str = Field(
        ...,
        description="Webhook event: order status (e.g. 'Paid', 'Ready to pick up', 'Delivered') or 'update_menu'",
    )
    storeId: str

    # Order-specific fields (required for order status events)
    PhoneNumber: Optional[str] = Field(
        None, description="Customer phone - required for order events"
    )
    trackingLink: Optional[str] = Field(None, description="Order tracking link")
    transactionId: Optional[str] = Field(
        None, description="Transaction ID - required for order events"
    )
    orderNumber: Optional[str] = Field(
        None, description="Order number - required for order events"
    )
    orderDate: Optional[str] = Field(
        None, description="Order date - required for order events"
    )

    # Menu update specific fields (required for update_menu event)
    brandId: Optional[str] = Field(
        None, description="Brand ID - required for update_menu event"
    )


class AdoraWebhookResponse(BaseModel):
    """Response body for Adora webhook"""

    status: str = "succeed"
