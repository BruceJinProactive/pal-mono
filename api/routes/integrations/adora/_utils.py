import asyncio
from datetime import datetime

from fastapi import Request
from sqlalchemy import desc, select
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
from db.tables.adora_orders import AdoraOrder
from db.tables.types import Channel, IntegrationProvider
from services.transaction_service import update_order_by_phone
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


def format_phone_number(phone_number: str | None) -> str:
    # Remove non-digit characters
    if not phone_number or not phone_number.isdigit() or len(phone_number) != 10:
        logger.warning(f"[AdoraWebhook] Invalid phone number: {phone_number}")
        return ""

    return "+1" + phone_number


async def update_order_status(
    session: AsyncSession, webhook_request: AdoraWebhookRequest
) -> AdoraOrder:
    """
    Update the status of an existing order in both orders and transactions tables.

    Args:
        session: The database session
        webhook_request: The validated webhook request data

    Returns:
        AdoraOrder: The updated order object

    Raises:
        ValueError: If the order is not found or has invalid store phone number
    """
    # Find the existing order using store_id and order_number

    logger.debug(f"[AdoraWebhook]Update order status: {webhook_request.OrderNumber}")

    phone_number = format_phone_number(webhook_request.PhoneNumber)
    if not phone_number:
        raise ValueError(
            f"[AdoraWebhook] PhoneNumber must be valid: {webhook_request.PhoneNumber}"
        )

    raw_date = webhook_request.OrderDate
    if raw_date is None:
        raise ValueError("[AdoraWebhook] OrderDate must not be None")
    dt = datetime.strptime(raw_date, "%m/%d/%Y %I:%M:%S %p")
    order_date = dt.date()
    start = datetime.combine(order_date, datetime.min.time())

    pending_order_query = (
        select(AdoraOrder)
        .where(
            AdoraOrder.store_id == webhook_request.storeId,
            AdoraOrder.status == "pending",
            AdoraOrder.user_phone_number == phone_number,
            AdoraOrder.order_date >= start,
        )
        .order_by(desc(AdoraOrder.created_at))
    )
    result = await session.execute(pending_order_query)
    rows = result.scalars().all()
    if len(rows) == 0:
        raise ValueError(
            f"Order not found with store_id: {webhook_request.storeId} "
            f"and phone_number: {webhook_request.PhoneNumber} "
            f"and OrderDate: {webhook_request.OrderDate}"
        )
    elif len(rows) == 1:
        order = rows[0]
    else:
        logger.warning(
            f"[AdoraWebhook] found multiple matched orders: {len(rows)}",
            extra={
                "store_id": webhook_request.storeId,
                "phone_number": webhook_request.PhoneNumber,
                "OrderDate": webhook_request.OrderDate,
            },
        )
        order = rows[0]

    # Update the order status in orders table (event should not be None for order type)
    if webhook_request.Event is not None:
        order.status = webhook_request.Event

    # If there's a tracking link in the webhook, update it
    if webhook_request.trackingLink:
        order.tracking_link = webhook_request.trackingLink

    # Also update the corresponding transaction in transactions table
    # Note: Using sync helper function, but the session will be committed later
    try:
        success = await asyncio.to_thread(
            update_order_by_phone,
            store_id=webhook_request.storeId,
            vendor=IntegrationProvider.adora,
            new_status=webhook_request.Event,
            user_phone_number=webhook_request.PhoneNumber,
            order_date=webhook_request.OrderDate,
            tracking_link=webhook_request.trackingLink,
        )

        if success:
            logger.debug(
                f"[AdoraWebhook] Successfully updated transaction for order {order.order_number}"
            )
        else:
            logger.warning(
                f"[AdoraWebhook] No transaction found for order {order.order_number} "
                f"with external_transaction_id {order.transaction_id}"
            )

    except Exception as e:
        logger.error(
            f"[AdoraWebhook] Error updating transaction for order {order.order_number}: {e}",
            exc_info=True,
        )
        # Don't fail the entire operation if transaction update fails

    await session.commit()

    # Refresh order to ensure we have the latest state from database
    await session.refresh(order)

    logger.info(
        f"[AdoraWebhook] Successfully updated order {order.order_number} status to {webhook_request.Event}"
    )

    # Return the complete order object
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


async def handle_order_threshold_update(
    session: AsyncSession, webhook_request: AdoraWebhookRequest
) -> dict:
    """
    Handle order threshold update webhook event.

    Updates the order_threshold in the project integration's config for the specified store.

    Args:
        session: The database session
        webhook_request: The validated webhook request data containing storeId and orderThreshold

    Returns:
        dict: Success/failure status with message

    Raises:
        ValueError: If project integration not found or orderThreshold is invalid
    """
    from db.tables.integration import ProjectIntegration

    logger.debug(
        f"[AdoraWebhook] Processing order threshold update for store: {webhook_request.storeId}, "
        f"threshold: {webhook_request.orderThreshold}"
    )

    # Validate order threshold value (allow None to remove limit)
    if (
        webhook_request.orderThreshold is not None
        and webhook_request.orderThreshold < 0
    ):
        raise ValueError("orderThreshold must be a non-negative number")

    # Find project integration by store_identifier (storeId)
    query = select(ProjectIntegration).where(
        ProjectIntegration.store_identifier == webhook_request.storeId
    )
    result = await session.execute(query)
    project_integration = result.scalar_one_or_none()

    if not project_integration:
        raise ValueError(
            f"Project integration not found for store_id: {webhook_request.storeId}"
        )

    # Update the order_threshold in project integration config
    if project_integration.config is None:
        project_integration.config = {}

    # Get existing config and update order_threshold
    config = dict(project_integration.config)

    if webhook_request.orderThreshold is None:
        # Remove order_threshold from config (unlimited orders)
        config.pop("order_threshold", None)
        message = "Order threshold removed (unlimited orders allowed)"
    else:
        # Set order_threshold to specified value
        config["order_threshold"] = webhook_request.orderThreshold
        message = f"Order threshold updated to {webhook_request.orderThreshold}"

    project_integration.config = config

    await session.commit()
    await session.refresh(project_integration)

    logger.info(
        f"[AdoraWebhook] Successfully updated order threshold for store {webhook_request.storeId}: {message}"
    )

    return {
        "status": "success",
        "message": message,
    }


def _generate_notification_text(order: AdoraOrder) -> str:
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
    order: AdoraOrder,
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
        logger.debug(
            "[AdoraWebhook]Send order status update message",
            extra={
                "order_number": order.order_number,
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
