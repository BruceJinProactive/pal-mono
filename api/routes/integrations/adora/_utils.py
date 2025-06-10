from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.tables.orders import Order

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
) -> None:
    """
    Update the status of an existing order in the database.

    Args:
        session: The database session
        webhook_request: The validated webhook request data

    Raises:
        ValueError: If the order is not found
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
