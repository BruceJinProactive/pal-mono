from enum import StrEnum
from typing import Optional

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


class ToastStockItemStatus(StrEnum):
    IN_STOCK = "IN_STOCK"
    QUANTITY = "QUANTITY"


class ToastWebhookStockItemDetails(BaseModel):
    """Details of the stock item updated event
    Example:
    {
      "itemGuid": "1e199622-ccbf-4ba8-8c37-111519dca13b",
      "restaurantGuid": "3325cc58-dc6e-4e21-85f9-7de275ffe820",
      "status": "IN_STOCK",
      "quantity": 10.0, (optional)
      "multiLocationId": "100000000171238879",
      "versionId": "1e199622-ccbf-4ba8-8c37-111519dca13b"
    }
    """

    itemGuid: str
    restaurantGuid: str
    status: ToastStockItemStatus
    multiLocationId: str
    versionId: str
    quantity: Optional[float] = None
