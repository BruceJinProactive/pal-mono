from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from db.pal_repository.data_classes.order import (
    LatestOrderData,
    OrderCustomerHistoryData,
    OrderData,
    OrderDetailsData,
)
from db.tables.conversations import Conversation
from db.tables.orders import Order
from db.tables.projects import Project
from utils.log import logger
from utils.phone import normalize_phone_digits


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
        display_payload=row.display_payload,
        fulfillment_strategy=row.fulfillment_strategy,
        order_time=row.order_time,
        updated_at=row.updated_at,
    )


def _to_latest_data(row: RowMapping) -> LatestOrderData:
    return LatestOrderData(
        id=row["id"],
        conversation_id=row["conversation_id"],
        created_at=row["created_at"],
        order_id=row["order_id"],
    )


def _to_details_data(row: RowMapping) -> OrderDetailsData:
    vendor = row["vendor"]
    return OrderDetailsData(
        id=row["id"],
        conversation_id=row["conversation_id"],
        created_at=row["created_at"],
        order_id=row["order_id"],
        store_id=row["store_id"],
        user_phone_number=row["user_phone_number"],
        store_phone_number=row["store_phone_number"],
        tracking_link=row["tracking_link"],
        status=row["status"],
        vendor=vendor.value if hasattr(vendor, "value") else vendor,
        subtotal=row["subtotal"],
        order_items=tuple(row["order_items"]) if row["order_items"] else (),
        display_payload=row["display_payload"],
        fulfillment_strategy=row["fulfillment_strategy"],
        updated_at=row["updated_at"],
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

    async def get_customer_history_by_project_id_and_phone(
        self, project_id: uuid.UUID, phone_number: str | None
    ) -> OrderCustomerHistoryData:
        """Summarize prior same-account orders for a caller phone."""
        target_digits = normalize_phone_digits(phone_number)
        if target_digits is None:
            return OrderCustomerHistoryData(order_count=0)

        phone_digits = func.regexp_replace(
            func.coalesce(Order.user_phone_number, ""),
            r"\D",
            "",
            "g",
        )
        conversation_project = aliased(Project)
        current_project = aliased(Project)
        current_account_id = (
            select(current_project.account_id)
            .filter(current_project.id == project_id)
            .scalar_subquery()
        )
        try:
            result = await self.session.execute(
                select(
                    func.count(Order.id).label("order_count"),
                    func.max(Order.created_at).label("last_order_at"),
                )
                .join(Conversation, Order.conversation_id == Conversation.id)
                .join(
                    conversation_project,
                    Conversation.project_id == conversation_project.id,
                )
                .filter(
                    conversation_project.account_id == current_account_id,
                    phone_digits == target_digits,
                )
            )
            row = result.mappings().one()
            return OrderCustomerHistoryData(
                order_count=int(row["order_count"] or 0),
                last_order_at=row["last_order_at"],
            )
        except SQLAlchemyError:
            await self.session.rollback()
            logger.exception("Error retrieving order customer history")
            raise

    async def get_latest_order_by_conversation_id(
        self,
        conversation_id: uuid.UUID,
    ) -> LatestOrderData | None:
        """Retrieve the newest order for a conversation."""
        try:
            sort_time = func.coalesce(Order.order_time, Order.created_at)
            result = await self.session.execute(
                select(
                    Order.id.label("id"),
                    Order.conversation_id.label("conversation_id"),
                    Order.created_at.label("created_at"),
                    Order.order_id.label("order_id"),
                )
                .filter(
                    Order.conversation_id == conversation_id,
                )
                .order_by(sort_time.desc(), Order.created_at.desc())
                .limit(1)
            )
            row = result.mappings().one_or_none()
            return _to_latest_data(row) if row else None
        except SQLAlchemyError:
            await self.session.rollback()
            logger.exception("Error retrieving latest order by conversation ID")
            raise

    async def get_latest_orders_by_conversation_ids(
        self,
        conversation_ids: Sequence[uuid.UUID],
    ) -> dict[uuid.UUID, LatestOrderData]:
        """Retrieve the newest order per conversation."""
        sanitized_conversation_ids = [
            conversation_id for conversation_id in conversation_ids if conversation_id
        ]
        if not sanitized_conversation_ids:
            return {}

        try:
            sort_time = func.coalesce(Order.order_time, Order.created_at)
            result = await self.session.execute(
                select(
                    Order.id.label("id"),
                    Order.conversation_id.label("conversation_id"),
                    Order.created_at.label("created_at"),
                    Order.order_id.label("order_id"),
                )
                .filter(
                    Order.conversation_id.in_(sanitized_conversation_ids),
                )
                .order_by(
                    Order.conversation_id,
                    sort_time.desc(),
                    Order.created_at.desc(),
                )
            )
            rows = result.mappings().all()
        except SQLAlchemyError:
            await self.session.rollback()
            logger.exception("Error retrieving latest orders by conversation IDs")
            raise

        latest_orders: dict[uuid.UUID, LatestOrderData] = {}
        for row in rows:
            conversation_id = row["conversation_id"]
            if conversation_id not in latest_orders:
                latest_orders[conversation_id] = _to_latest_data(row)
        return latest_orders

    async def get_latest_order_details_by_conversation_id(
        self,
        conversation_id: uuid.UUID,
    ) -> OrderDetailsData | None:
        """Retrieve the newest order detail projection for a conversation.

        This intentionally does not select Order.order_time because some historic
        rows contain postgres infinity timestamps that psycopg cannot deserialize.
        """
        try:
            sort_time = func.coalesce(Order.order_time, Order.created_at)
            result = await self.session.execute(
                select(
                    Order.id.label("id"),
                    Order.conversation_id.label("conversation_id"),
                    Order.created_at.label("created_at"),
                    Order.order_id.label("order_id"),
                    Order.store_id.label("store_id"),
                    Order.user_phone_number.label("user_phone_number"),
                    Order.store_phone_number.label("store_phone_number"),
                    Order.tracking_link.label("tracking_link"),
                    Order.status.label("status"),
                    Order.vendor.label("vendor"),
                    Order.subtotal.label("subtotal"),
                    Order.order_items.label("order_items"),
                    Order.display_payload.label("display_payload"),
                    Order.fulfillment_strategy.label("fulfillment_strategy"),
                    Order.updated_at.label("updated_at"),
                )
                .filter(
                    Order.conversation_id == conversation_id,
                )
                .order_by(sort_time.desc(), Order.created_at.desc())
                .limit(1)
            )
            row = result.mappings().one_or_none()
            return _to_details_data(row) if row else None
        except SQLAlchemyError:
            await self.session.rollback()
            logger.exception("Error retrieving latest order details by conversation ID")
            raise
