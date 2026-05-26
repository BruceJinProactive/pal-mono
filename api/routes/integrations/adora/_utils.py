import asyncio

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

import services.relay_service as relay_service
from api.schemas.chat.message import (
    AuthorType,
    Broker,
    Extras,
    Message,
    Metadata,
    TextObject,
)
from db.tables.types import Channel, IntegrationProvider
from services.transaction_service import (
    OrderStatusUpdateResult,
    update_order_from_webhook,
)
from utils.log import logger

from .schemas import AdoraWebhookRequest


def is_dev_mode(request: Request) -> bool:
    """
    Check if the request has a 'dev' header set to true.
    This is used to activate development-specific workflows.
    TODO: remove this once we're done testing

    Args:
        request: The FastAPI request object

    Returns:
        bool: True if dev mode is enabled, False otherwise
    """
    dev_header = request.headers.get("dev", "false").lower()
    return dev_header == "true"


async def update_order_status(
    session: AsyncSession, webhook_request: AdoraWebhookRequest
) -> OrderStatusUpdateResult:
    """
    Update the status of an existing order in the generic orders table.

    Args:
        session: The database session
        webhook_request: The validated webhook request data

    Returns:
        OrderStatusUpdateResult: The updated order snapshot

    Raises:
        ValueError: If the order is not found or has invalid store phone number
    """
    del session
    logger.debug(f"[AdoraWebhook]Update order status: {webhook_request.OrderNumber}")

    normalized_status = (
        "paid" if webhook_request.Event == "Paid" else webhook_request.Event
    )
    if normalized_status is None:
        raise ValueError("[AdoraWebhook] Event must not be None")

    order = await asyncio.to_thread(
        update_order_from_webhook,
        store_id=webhook_request.storeId,
        vendor=IntegrationProvider.adora,
        new_status=normalized_status,
        order_id=webhook_request.OrderNumber,
        alternate_order_id=webhook_request.transactionId,
        user_phone_number=webhook_request.PhoneNumber,
        order_date=webhook_request.OrderDate,
        tracking_link=webhook_request.trackingLink,
    )

    if order is None:
        raise ValueError(
            "Order not found in orders table with "
            f"store_id: {webhook_request.storeId} "
            f"order_number: {webhook_request.OrderNumber} "
            f"transaction_id: {webhook_request.transactionId} "
            f"and phone_number: {webhook_request.PhoneNumber} "
            f"and OrderDate: {webhook_request.OrderDate}"
        )

    logger.info(
        f"[AdoraWebhook] Successfully updated order {order.order_id} status to {normalized_status}"
    )

    return order


async def handle_menu_update(
    session: AsyncSession, webhook_request: AdoraWebhookRequest
) -> dict:
    """
    Handle menu update webhook event.

    Args:
        session: The database session
        webhook_request: The validated webhook request data

    Returns:
        dict: Success/failure status

    Raises:
        ValueError: If required fields are missing for update_menu event
    """

    logger.debug(
        f"[AdoraWebhook] Processing menu update for store: {webhook_request.storeId}"
    )

    return {"status": "success", "message": "Menu update processed successfully"}


def _generate_notification_text(order: OrderStatusUpdateResult) -> str:
    """
    Generate notification text based on the event type. Currently, only use a single message format for simplicity, later we may want to create different messages case by case.

    Args:
        order: The order object from the database
        event_status: The event status from the webhook

    Returns:
        str: The generated notification text
    """
    order_label = order.order_id or str(order.id)
    base_msg = f"Order #{order_label} status: {order.status}"

    if order.tracking_link:
        return f"{base_msg} - Track here: {order.tracking_link}"

    return base_msg


async def send_order_notification(
    order: OrderStatusUpdateResult,
) -> None:
    """
    Send order notification through the relay service.

    Args:
        order: The order object from the database

    Raises: RuntimeError: If the notification fails to send due to status error or any other exception
        ValueError: If phone numbers are invalid
    """
    # Validate phone numbers before sending notification
    if not order.store_phone_number or not order.store_phone_number.strip():
        raise ValueError(f"Invalid store phone number for order {order.order_id}")

    if not order.user_phone_number or not order.user_phone_number.strip():
        raise ValueError(f"Invalid user phone number for order {order.order_id}")

    # Generate notification text using the order's current status
    notification_text = _generate_notification_text(order)

    notification_message = Message(
        author_type=AuthorType.SYSTEM,
        sender_identifier=order.store_phone_number,
        recipient_identifier=order.user_phone_number,
        channel=Channel.SMS,
        broker=Broker.TWILIO,
        text=TextObject(body=notification_text),
        metadata=Metadata(testing=False),
        extras=Extras(),
    )

    try:
        response = relay_service.send_message(notification_message)
        logger.debug(
            "[AdoraWebhook]Send order status update message",
            extra={
                "order_id": order.order_id,
                "from": order.store_phone_number,
                "to": order.user_phone_number,
            },
        )
        if response.get("status") != "scheduled":
            error_msg = response.get("error_message", "Unknown error")
            logger.error(f"Failed to send notification: {error_msg}")
            raise RuntimeError(f"Failed to send notification: {error_msg}")
    except Exception as e:
        logger.error(f"Exception occurred while sending notification: {e}")
        raise
