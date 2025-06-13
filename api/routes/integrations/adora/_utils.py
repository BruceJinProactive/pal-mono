from fastapi import Request
from sqlalchemy import select
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
from db.tables.orders import Order
from db.tables.types import Channel
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
) -> Order:
    """
    Update the status of an existing order in the database.

    Args:
        session: The database session
        webhook_request: The validated webhook request data

    Returns:
        Order: The updated order object

    Raises:
        ValueError: If the order is not found or has invalid store phone number
    """
    # Find the existing order using store_id and order_number
    order_query = select(Order).where(
        Order.store_id == webhook_request.storeId,
        Order.order_number == webhook_request.orderNumber,
    )
    result = await session.execute(order_query)
    order = result.scalar_one_or_none()

    if not order:
        raise ValueError(
            f"Order not found with store_id: {webhook_request.storeId} "
            f"and order_number: {webhook_request.orderNumber}"
        )

    # Update the order status
    order.status = webhook_request.event

    # If there's a tracking link in the webhook, update it
    if webhook_request.trackingLink:
        order.tracking_link = webhook_request.trackingLink

    await session.commit()

    # Refresh order to ensure we have the latest state from database
    await session.refresh(order)

    # Return the complete order object
    return order


def _generate_notification_text(order: Order) -> str:
    """
    Generate notification text based on the event type. Currently, only use a single message format for simplicity, later we may want to create different messages case by case.

    Args:
        order: The order object from the database
        event_status: The event status from the webhook

    Returns:
        str: The generated notification text
    """
    base_msg = f"Order #{order.order_number} status: {order.status}"

    if order.tracking_link:
        return f"{base_msg} - Track here: {order.tracking_link}"

    return base_msg


async def send_order_notification(
    order: Order,
) -> None:
    """
    Send order notification through the relay service.

    Args:
        order: The order object from the database

    Raises:
        RuntimeError: If the notification fails to send due to status error or any other exception
        ValueError: If phone numbers are invalid
    """
    # Validate phone numbers before sending notification
    if not order.store_phone_number or not order.store_phone_number.strip():
        raise ValueError(f"Invalid store phone number for order {order.order_number}")

    if not order.user_phone_number or not order.user_phone_number.strip():
        raise ValueError(f"Invalid user phone number for order {order.order_number}")

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
        if response.get("status") != "scheduled":
            error_msg = response.get("error_message", "Unknown error")
            logger.error(f"Failed to send notification: {error_msg}")
            raise RuntimeError(f"Failed to send notification: {error_msg}")
    except Exception as e:
        logger.error(f"Exception occurred while sending notification: {e}")
        raise
