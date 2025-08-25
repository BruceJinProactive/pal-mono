import json

from fastapi import Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from utils.log import logger

from ._utils import (
    update_menu_content,
    update_ordering_schedule,
    update_stock_item_status,
)
from .schema import ToastWebhookRequest, ToastWebhookResponse


async def api_toast_webhook(request: Request) -> JSONResponse:
    """
    Process incoming webhook requests from Toast.
    Authentication and validation are handled by AWS API Gateway.

    Args:
        request: The FastAPI request object

    Returns:
        JSONResponse: The response to send back to Toast

    Raises:
        HTTPException: If there's an error processing the request
    """
    # Extract body from request
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError) as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": f"Invalid JSON in request body: {str(e)}"},
        )

    # Validate request body against schema
    try:
        webhook_request = ToastWebhookRequest(**body)

        # Handle webhook events
        match webhook_request.eventCategory:
            case "menus":
                await update_menu_content(webhook_request)
            case "stock":
                await update_stock_item_status(webhook_request)
            case "ordering_schedule":
                await update_ordering_schedule(webhook_request)
            case _:
                logger.warning(
                    f"[ToastWebhook.api_toast_webhook] Received unknown Toast webhook event category: {webhook_request.eventCategory}"
                )
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content=ToastWebhookResponse().model_dump(exclude_none=True),
                )
    except ValidationError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": f"Invalid request body: {str(e)}"},
        )

    # Log the incoming request for debugging
    logger.debug(
        "[ToastWebhook.api_toast_webhook] Toast webhook request received",
        extra={
            "timestamp": webhook_request.timestamp,
            "event_category": webhook_request.eventCategory,
            "event_type": webhook_request.eventType,
            "guid": webhook_request.guid,
        },
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=ToastWebhookResponse().model_dump(exclude_none=True),
    )
