import json

from fastapi import Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from db.session import AsyncSessionLocal
from utils.log import logger

from ._utils import send_order_notification, update_order_status
from .schemas import AdoraWebhookRequest, AdoraWebhookResponse


async def api_adora_webhook(request: Request) -> JSONResponse:
    """
    Process incoming webhook requests from Palona for order status updates.
    Authentication and validation are handled by AWS API Gateway.

    Args:
        request: The FastAPI request object

    Returns:
        JSONResponse: The response to send back to Palona

    Raises:
        HTTPException: If there's an error processing the request
    """
    try:
        # Extract body from request
        body = await request.json()

        # Validate request format
        if not isinstance(body, dict):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"error": "Invalid request format"},
            )

        # Log the incoming request for debugging
        logger.debug(
            "[AdoraWebhook]Adora webhook request received",
            extra={
                "event": body.get("event"),
                "store_id": body.get("storeId"),
                "order_number": body.get("orderNumber"),
            },
        )

        # Validate request body against schema
        try:
            webhook_request = AdoraWebhookRequest(**body)
        except ValidationError as e:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"error": f"Invalid request body: {str(e)}"},
            )

        # Initialize database session
        async with AsyncSessionLocal() as session:
            try:
                # Update order status and get order object
                order = await update_order_status(session, webhook_request)

                # Attempt to send notification
                await send_order_notification(order)

            except (SQLAlchemyError, ValueError, RuntimeError) as e:
                logger.error(f"Failed to update order: {str(e)}")
                return JSONResponse(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    content={"error": f"Failed to update order: {str(e)}"},
                )

        # For now, just log the event
        logger.info(
            f"Order status update received - Order: {webhook_request.orderNumber}, Event: {webhook_request.event}",
            extra={
                "store_id": webhook_request.storeId,
                "transaction_id": webhook_request.transactionId,
                "phone_number": webhook_request.PhoneNumber,
                "tracking_link": webhook_request.trackingLink,
                "order_date": webhook_request.orderDate,
            },
        )

        # Return success response
        return JSONResponse(content=AdoraWebhookResponse().model_dump())

    except json.JSONDecodeError:
        logger.error("Invalid JSON in request body")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Invalid JSON in request body"},
        )
    except Exception as e:
        logger.error(f"Error processing Adora webhook request: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "Internal server error"},
        )
