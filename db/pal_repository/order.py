from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.order import OrderData
from db.tables.orders import Order
from utils.log import logger


def _to_data(row: Order) -> OrderData:
    """Convert an ORM Order to an OrderData."""
    return OrderData(
        id=row.id,
        conversation_id=row.conversation_id,
        created_at=row.created_at,
        order_id=row.order_id,
        store_id=row.store_id,
        user_phone_number=row.user_phone_number,
        store_phone_number=row.store_phone_number,
        tracking_link=row.tracking_link,
        status=row.status,
        vendor=row.vendor.value if row.vendor else None,
        subtotal=row.subtotal,
        order_items=tuple(row.order_items) if row.order_items else (),
        fulfillment_strategy=row.fulfillment_strategy,
        order_time=row.order_time,
        updated_at=row.updated_at,
    )


class OrderRepository:
    """Async-only repository for Order records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, order_id: uuid.UUID) -> OrderData | None:
        """Retrieve an order by ID."""
        try:
            result = await self.session.execute(
                select(Order).filter(Order.id == order_id)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except SQLAlchemyError:
            await self.session.rollback()
            logger.exception("Error retrieving order by ID")
            raise

    async def get_by_conversation_id(
        self, conversation_id: uuid.UUID
    ) -> list[OrderData]:
        """Retrieve all orders for a conversation."""
        try:
            result = await self.session.execute(
                select(Order)
                .filter(Order.conversation_id == conversation_id)
                .order_by(Order.created_at.desc())
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except SQLAlchemyError:
            await self.session.rollback()
            logger.exception("Error retrieving orders by conversation ID")
            raise
