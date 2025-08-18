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

    status: str = "Success"


class ToastWebhookMenuDetails(BaseModel):
    """Details of the menu updated event
    Example:
    {
        "restaurantGuid": "00000000-1111-2222-3333-444444444444",
        "publishedDate": "2021-10-06T20:11:01.737Z"
    }

    """

    restaurantGuid: str
    publishedDate: str
