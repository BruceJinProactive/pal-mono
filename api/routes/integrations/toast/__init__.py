from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from api.schemas.error.error import ErrorResponse

from ._implementation import api_toast_webhook

toast_router = APIRouter(prefix="/toast", tags=["Integrations"])


@toast_router.post(
    "/event",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Successful response", "model": dict},
        400: {"model": ErrorResponse},
        401: {"description": "Unauthorized"},
        500: {"model": ErrorResponse},
    },
)
async def toast_webhook(
    request: Request,
) -> JSONResponse:
    """
    Endpoint to receive order status updates from Toast.
    Handles incoming requests according to the Toast Webhook specification.

    Expected request body:
        {
            "timestamp": "<ISO formatted timestamp in UTC>",
            "eventCategory": "<eventCategory>",
            "eventType": "<eventType>",
            "guid": "<eventGuid>",
            "details": {
                <eventType specific payload>
        }
        }
    """
    return await api_toast_webhook(request)
