from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

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
    Endpoint to receive order status updates from Palona.
    Handles incoming requests according to the Palona Webhook specification.

    Expected request body:
    {
        "event": string,           // e.g. Paid, Ready to pick up, Picked up, Delivered, etc.
        "PhoneNumber": string,
        "trackingLink": string,
        "storeId": string,
        "transactionId": string,
        "orderNumber": string,
        "orderDate": string
    }
    """
    return await api_adora_webhook(request)
