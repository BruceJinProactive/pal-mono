import json

from fastapi import Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from db.session import AsyncSessionLocal
from utils.log import logger

from ._utils import handle_menu_update, send_order_notification, update_order_status
from .schemas import AdoraWebhookRequest


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
            extra={"webhook_body": body},
        )

        # Validate request body against schema
        try:
            webhook_request = AdoraWebhookRequest(**body)
        except ValidationError as e:
            error_msg = f"Validation error for webhook request: {e}"
            logger.warning(error_msg)

            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"error": f"Invalid request body: {str(e)}"},
            )

        # Initialize database session
        async with AsyncSessionLocal() as session:
            try:
                # Route based on event type
                if webhook_request.Event == "update_menu":
                    logger.debug(
                        f"[AdoraWebhook] handling Adora webhook {webhook_request.Event} event",
                        extra={"webhook_body": body},
                    )

                    # Handle menu update
                    if not webhook_request.brandId:
                        return JSONResponse(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            content={
                                "error": "Missing required field for update_menu event: brandId"
                            },
                        )

                    result = await handle_menu_update(session, webhook_request)

                    if result["status"] == "success":
                        return JSONResponse(
                            status_code=status.HTTP_200_OK,
                            content=result,
                        )
                    else:
                        return JSONResponse(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            content=result,
                        )

                elif webhook_request.Event == "Paid":
                    # Handle order status events ("Paid")
                    # Validate required fields for order events
                    logger.debug(
                        f"[AdoraWebhook] handling Adora webhook {webhook_request.Event} event",
                        extra={"webhook_body": body},
                    )

                    if not all(
                        [
                            webhook_request.PhoneNumber,
                            webhook_request.transactionId,
                            webhook_request.OrderNumber,
                            webhook_request.OrderDate,
                            webhook_request.storeId,
                        ]
                    ):
                        logger.error(
                            f"[AdoraWebhook] Missing required payload for event: {webhook_request.Event}",
                            extra={"webhook_body": body},
                        )

                        return JSONResponse(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            content={
                                "error": "Missing required fields for order events: PhoneNumber, transactionId, OrderNumber, OrderDate"
                            },
                        )

                    # Update order status and get order object
                    order = await update_order_status(session, webhook_request)

                    # Attempt to send notification (do not fail webhook on notification errors)
                    try:
                        await send_order_notification(order)
                    except Exception as e:
                        logger.error(
                            f"[AdoraWebhook] Failed to send notification for order {order.order_id} "
                            f"(store: {order.store_id}, status: {order.status}): {e}",
                            exc_info=True,
                        )
                        # Continue processing - do not fail webhook due to notification errors

                    # Return success response
                    return JSONResponse(
                        status_code=status.HTTP_200_OK,
                        content={
                            "status": "success",
                            "message": "Order status updated successfully",
                        },
                    )
                else:
                    logger.debug(
                        f"[AdoraWebhook] Can not handle Adora webhook event: {webhook_request.Event}",
                        extra={"webhook_body": body},
                    )
                    # Return success response
                    return JSONResponse(
                        status_code=status.HTTP_200_OK,
                        content={
                            "status": "success",
                            "message": f"Adora webhook event:{webhook_request.Event} received successfully",
                        },
                    )

            except ValueError as e:
                # Handle validation errors with 400 status
                await session.rollback()
                error_msg = f"Validation error for {webhook_request.Event} webhook: {e}"
                logger.warning(error_msg)
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={"error": error_msg},
                )
            except (SQLAlchemyError, RuntimeError) as e:
                # Handle system/database errors with 500 status
                await session.rollback()
                error_msg = f"Failed to process {webhook_request.Event} webhook: {e}"
                logger.exception(error_msg)
                return JSONResponse(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    content={"error": error_msg},
                )

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
