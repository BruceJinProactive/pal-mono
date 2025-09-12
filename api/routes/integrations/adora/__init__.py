from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

import db
from api.routes.endpoints import endpoints
from api.schemas.error.error import ErrorResponse

from ._implementation import api_adora_webhook

adora_router = APIRouter(prefix="/adora", tags=["Integrations"])


@adora_router.post(
    "/event",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Successful response", "model": dict},
        400: {"model": ErrorResponse},
        401: {"description": "Unauthorized"},
        500: {"model": ErrorResponse},
    },
)
async def adora_webhook(
    request: Request,
) -> JSONResponse:
    """
    Endpoint to receive webhooks from Palona for both order status updates and menu updates.
    Handles incoming requests according to the Palona Webhook specification.

    Request body format based on the 'event' field:

    For order status updates:
    {
        "event": string,           // e.g. Paid, Ready to pick up, Picked up, Delivered, etc.
        "storeId": string,         // Store identifier
        "PhoneNumber": string,     // Customer phone number
        "trackingLink": string,    // Optional tracking link
        "transactionId": string,   // Transaction identifier
        "orderNumber": string,     // Order number
        "orderDate": string        // Order date
    }

    For menu updates:
    {
        "event": "update_menu",
        "storeId": string,         // Store identifier
        "brandId": string          // Brand identifier
    }

    Menu update events are processed and logged for tracking purposes.
    """
    return await api_adora_webhook(request)
