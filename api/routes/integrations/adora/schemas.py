from typing import Optional

from pydantic import BaseModel, Field


class AdoraWebhookRequest(BaseModel):
    """Request body for Adora webhook

    Required parameters by event:

    For order status events (e.g., 'Paid', 'Ready to pick up', 'Delivered'):
    - Event, storeId, PhoneNumber, transactionId, OrderNumber, OrderDate
    - trackingLink (optional)

    For menu update events ('update_menu'):
    - Event, storeId, brandId

    For order threshold update events ('update_order_threshold'):
    - Event, storeId
    - orderThreshold (optional): If omitted/null, removes the limit
    """

    # Required fields
    Event: str = Field(
        ...,
        description="Webhook event: order status (e.g. 'Paid', 'Ready to pick up', 'Delivered'), 'update_menu', or 'update_order_threshold'",
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
    OrderNumber: Optional[str] = Field(
        None, description="Order number - required for order events"
    )
    OrderDate: Optional[str] = Field(
        None, description="Order date - required for order events"
    )

    # Menu update specific fields (required for update_menu event)
    brandId: Optional[str] = Field(
        None, description="Brand ID - required for update_menu event"
    )

    # Order threshold update specific fields (optional for update_order_threshold event)
    orderThreshold: Optional[float] = Field(
        None,
        description="Order threshold amount in dollars. If omitted/null, removes the limit (allows unlimited orders). If 0, disables AI ordering. If > 0, sets maximum order amount.",
    )


class AdoraWebhookResponse(BaseModel):
    """Response body for Adora webhook"""

    status: str = "succeed"
