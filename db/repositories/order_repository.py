import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional, Sequence

from sqlalchemy import case, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db.pal_repository.data_classes.order import LatestOrderData, OrderDetailsData
from db.tables import Account, Conversation, Message, Project, User
from db.tables.orders import Order
from db.tables.types import IntegrationProvider
from utils.log import logger


def _to_latest_order_data(row: Any) -> LatestOrderData:
    return LatestOrderData(
        id=row.id,
        conversation_id=row.conversation_id,
        created_at=row.created_at,
        order_id=row.order_id,
    )


def _to_order_details_data(row: Any) -> OrderDetailsData:
    vendor = row.vendor.value if hasattr(row.vendor, "value") else row.vendor
    return OrderDetailsData(
        id=row.id,
        conversation_id=row.conversation_id,
        created_at=row.created_at,
        order_id=row.order_id,
        store_id=row.store_id,
        user_phone_number=row.user_phone_number,
        store_phone_number=row.store_phone_number,
        tracking_link=row.tracking_link,
        status=row.status,
        vendor=vendor,
        subtotal=row.subtotal,
        order_items=tuple(row.order_items) if row.order_items else (),
        fulfillment_strategy=row.fulfillment_strategy,
        updated_at=row.updated_at,
    )


class OrderRepository:
    """Repository for managing order database operations."""

    def __init__(self, session: Session, auto_commit: bool = True):
        self.session = session
        self.auto_commit = auto_commit

    def create_order(
        self,
        conversation_id: uuid.UUID,
        vendor: Optional[IntegrationProvider] = None,
        order_id: Optional[str] = None,
        store_id: Optional[str] = None,
        user_phone_number: Optional[str] = None,
        store_phone_number: Optional[str] = None,
        tracking_link: Optional[str] = None,
        status: Optional[str] = None,
        fulfillment_strategy: Optional[str] = None,
        subtotal: Optional[Decimal] = None,
        order_items: Optional[list] = None,
        order_time: Optional[datetime] = None,
    ) -> Order:
        """
        Create an order record.

        Args:
            conversation_id: The conversation this order belongs to (required)
            vendor: The integration provider/vendor
            order_id: Order identifier from external system
            store_id: Store/location identifier
            user_phone_number: Customer's phone number
            store_phone_number: Store's phone number
            tracking_link: Link to track the order
            status: Current status of the order
            fulfillment_strategy: Strategy for fulfilling the order
            subtotal: Order subtotal amount
            order_items: List of items in the order
            order_time: When the order was placed
        Returns:
            Order: The created order record
        """
        order = Order(
            order_id=order_id,
            store_id=store_id,
            user_phone_number=user_phone_number,
            store_phone_number=store_phone_number,
            tracking_link=tracking_link,
            status=status,
            fulfillment_strategy=fulfillment_strategy,
            conversation_id=conversation_id,
            vendor=vendor,
            subtotal=subtotal,
            order_items=order_items or [],
            order_time=order_time,
        )

        self.session.add(order)
        if self.auto_commit:
            self.session.commit()
        return order

    def get_order_by_id(self, order_id: uuid.UUID) -> Optional[Order]:
        """Get an order by its ID."""
        return self.session.query(Order).filter(Order.id == order_id).first()

    def get_order_by_order_id_store_vendor(
        self,
        order_id: str,
        store_id: str,
        vendor: IntegrationProvider,
    ) -> Optional[Order]:
        """
        Get an order by its order ID, store ID, and vendor.

        Args:
            order_id: The order ID to find
            store_id: The store ID to find
            vendor: The integration provider (adora, square, toast, etc.)

        Returns:
            Order: The order if found, or None if not found
        """
        filters = [
            Order.order_id == order_id,
            Order.vendor == vendor,
            Order.store_id == store_id,
        ]
        return self.session.query(Order).filter(*filters).first()

    def get_latest_order_by_external_ids(
        self,
        store_id: str,
        vendor: IntegrationProvider,
        order_ids: Sequence[str],
    ) -> Optional[Order]:
        """
        Get the newest order matching any external order identifier.

        Args:
            store_id: Store/location identifier.
            vendor: Integration provider.
            order_ids: Candidate external order identifiers.

        Returns:
            Order: The newest matching order, or None if not found.
        """
        sanitized_order_ids = [order_id for order_id in order_ids if order_id]
        if not sanitized_order_ids:
            return None

        try:
            return (
                self.session.query(Order)
                .filter(
                    Order.store_id == store_id,
                    Order.vendor == vendor,
                    Order.order_id.in_(sanitized_order_ids),
                )
                .order_by(Order.created_at.desc())
                .first()
            )
        except SQLAlchemyError:
            self.session.rollback()
            raise

    def get_latest_order_by_conversation_id(
        self,
        conversation_id: uuid.UUID,
    ) -> Optional[LatestOrderData]:
        """
        Get the newest order for a conversation.

        Args:
            conversation_id: Conversation identifier to match.

        Returns:
            LatestOrderData: The newest matching order projection, or None if no such
            order exists.
        """
        try:
            sort_time = func.coalesce(Order.order_time, Order.created_at)
            row = (
                self.session.query(Order)
                .with_entities(
                    Order.id,
                    Order.conversation_id,
                    Order.created_at,
                    Order.order_id,
                )
                .filter(
                    Order.conversation_id == conversation_id,
                )
                .order_by(sort_time.desc(), Order.created_at.desc())
                .first()
            )
            return _to_latest_order_data(row) if row else None
        except SQLAlchemyError:
            self.session.rollback()
            raise

    def get_latest_orders_by_conversation_ids(
        self,
        conversation_ids: Sequence[uuid.UUID],
    ) -> dict[uuid.UUID, LatestOrderData]:
        """
        Get the newest order for each conversation.

        Args:
            conversation_ids: Conversation identifiers to match.

        Returns:
            Mapping of conversation ID to its newest matching order projection.
        """
        sanitized_conversation_ids = [
            conversation_id for conversation_id in conversation_ids if conversation_id
        ]
        if not sanitized_conversation_ids:
            return {}

        try:
            sort_time = func.coalesce(Order.order_time, Order.created_at)
            rows = (
                self.session.query(Order)
                .with_entities(
                    Order.id,
                    Order.conversation_id,
                    Order.created_at,
                    Order.order_id,
                )
                .filter(
                    Order.conversation_id.in_(sanitized_conversation_ids),
                )
                .order_by(
                    Order.conversation_id,
                    sort_time.desc(),
                    Order.created_at.desc(),
                )
                .all()
            )
        except SQLAlchemyError:
            self.session.rollback()
            raise

        latest_orders: dict[uuid.UUID, LatestOrderData] = {}
        for row in rows:
            if row.conversation_id not in latest_orders:
                latest_orders[row.conversation_id] = _to_latest_order_data(row)
        return latest_orders

    def get_latest_order_details_by_conversation_id(
        self,
        conversation_id: uuid.UUID,
    ) -> Optional[OrderDetailsData]:
        """
        Get the newest order detail projection for a conversation.

        This intentionally does not select Order.order_time because some historic
        rows contain postgres infinity timestamps that psycopg cannot deserialize.
        """
        try:
            sort_time = func.coalesce(Order.order_time, Order.created_at)
            row = (
                self.session.query(Order)
                .with_entities(
                    Order.id,
                    Order.conversation_id,
                    Order.created_at,
                    Order.order_id,
                    Order.store_id,
                    Order.user_phone_number,
                    Order.store_phone_number,
                    Order.tracking_link,
                    Order.status,
                    Order.vendor,
                    Order.subtotal,
                    Order.order_items,
                    Order.fulfillment_strategy,
                    Order.updated_at,
                )
                .filter(
                    Order.conversation_id == conversation_id,
                )
                .order_by(sort_time.desc(), Order.created_at.desc())
                .first()
            )
            return _to_order_details_data(row) if row else None
        except SQLAlchemyError:
            self.session.rollback()
            raise

    def get_latest_order_by_phone_since(
        self,
        store_id: str,
        vendor: IntegrationProvider,
        user_phone_number: str,
        order_time_start: datetime,
        pending_only: bool,
    ) -> Optional[Order]:
        """
        Get the newest order matching store, vendor, phone, and order date floor.

        Args:
            store_id: Store/location identifier.
            vendor: Integration provider.
            user_phone_number: Normalized customer phone number.
            order_time_start: Start of the order date window.
            pending_only: Whether to only consider pending orders.

        Returns:
            Order: The newest matching order, or None if not found.
        """
        try:
            query = self.session.query(Order).filter(
                Order.store_id == store_id,
                Order.vendor == vendor,
                Order.user_phone_number == user_phone_number,
                Order.order_time >= order_time_start,
            )
            if pending_only:
                query = query.filter(Order.status == "pending")

            return query.order_by(Order.created_at.desc()).first()
        except SQLAlchemyError:
            self.session.rollback()
            raise

    def update_order_by_order_id(
        self,
        store_id: str,
        vendor: IntegrationProvider,
        order_id: str,
        **kwargs,
    ) -> Optional[Order]:
        """
        Update an order by its order ID, store ID, and vendor.

        Args:
            store_id: The store ID to find
            vendor: The integration provider (adora, square, toast, etc.)
            order_id: The order ID to find
            **kwargs: Fields to update (status, tracking_link, etc.)

        Returns:
            Order: The updated order, or None if not found
        """
        # Build query filters
        filters = [
            Order.order_id == order_id,
            Order.vendor == vendor,
            Order.store_id == store_id,
        ]

        # Find the order with all specified criteria
        order = self.session.query(Order).filter(*filters).first()

        if order:
            # Update order fields
            for field, value in kwargs.items():
                if hasattr(order, field):
                    setattr(order, field, value)

            # Always update order_time to current time
            order.order_time = datetime.now()

            if self.auto_commit:
                self.session.commit()

        return order

    def get_order_value(
        self,
        account_id: uuid.UUID,
        start_date: datetime,
        end_date: datetime,
    ):
        """
        Calculate order totals for a given account within a date range,
        grouped by channel and project. Only includes completed orders.
        Args:
            account_id (uuid.UUID): The account ID to filter orders by
            start_date (datetime): Start date for the calculation
            end_date (datetime): End date for the calculation
        Returns:
            list: Raw query results with date, channel, project_id, project_name, and order_total fields.
        """
        try:
            # Define expressions for efficient querying
            date_expr = func.date(Order.order_time)

            # Get channel from the first message in each conversation to avoid duplication
            # Use a subquery to get the channel for each conversation, ordered deterministically
            channel_subquery = (
                select(
                    Message.conversation_id,
                    Message.body["channel"].astext.label("channel"),
                )
                .where(
                    Message.body["channel"].isnot(None)
                )  # Exclude messages without channel
                .order_by(Message.conversation_id, Message.created_at.asc())
                .distinct(Message.conversation_id)
                .subquery()
            )

            # Query to get order totals by joining orders -> conversations -> channel_subquery -> projects
            # Group by date, channel, and project
            # Only include completed orders
            query = (
                select(
                    date_expr.label("date"),
                    channel_subquery.c.channel.label("channel"),
                    Conversation.project_id.label("project_id"),
                    Project.name.label("project_name"),
                    func.coalesce(func.sum(Order.subtotal), 0).label("order_total"),
                )
                .join(Conversation, Order.conversation_id == Conversation.id)
                .join(
                    channel_subquery,
                    Conversation.id == channel_subquery.c.conversation_id,
                )
                .join(User, Conversation.user_id == User.id)
                .join(Project, Conversation.project_id == Project.id)
                .filter(
                    User.account_id == account_id,
                    Order.order_time >= start_date,
                    Order.order_time <= end_date,
                    Order.subtotal.isnot(None),  # Only include orders with subtotals
                    Order.status != "pending",  # Exclude pending orders
                )
                .group_by(
                    date_expr,
                    channel_subquery.c.channel,
                    Conversation.project_id,
                    Project.name,
                )
                .order_by(
                    date_expr, channel_subquery.c.channel, Conversation.project_id
                )
            )
            result = self.session.execute(query)
            rows = result.all()
            return rows
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error calculating order values: {e}")
            return []

    def get_order_conversation_counts_by_account(
        self,
        account_id: uuid.UUID | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[tuple[uuid.UUID | None, str, int, int]]:
        """
        Get conversation counts based on orders (placed and paid), grouped by account.
        Always includes a TOTAL row with aggregated data.

        Args:
            account_id: Optional account ID. If provided, gets data for single account.
                       If None, gets data for all accounts.
            start_date: Optional start date for filtering orders. If None, no start limit.
            end_date: Optional end date for filtering orders. If None, no end limit.

        Returns:
            list[tuple[uuid.UUID | None, str, int, int]]: List of tuples (account_id, account_name, conversations_with_orders, conversations_with_paid_orders)
                        Last row will always be (None, 'TOTAL', total_orders, total_paid)
        """
        try:
            query = (
                self.session.query(
                    Account.id,
                    Account.name,
                    func.count(func.distinct(Conversation.id)).label("placed_order"),
                    func.count(
                        func.distinct(
                            case(
                                (func.lower(Order.status) == "paid", Conversation.id),
                                else_=None,
                            )
                        )
                    ).label("paid_order"),
                )
                .join(User, Account.id == User.account_id)
                .join(Conversation, User.id == Conversation.user_id)
                .join(
                    Order, Conversation.id == Order.conversation_id
                )  # INNER JOIN - only conversations with orders
            )

            # Add date filtering if provided (filter by order creation time)
            if start_date:
                query = query.filter(Order.order_time >= start_date)
            if end_date:
                query = query.filter(Order.order_time <= end_date)

            if account_id:
                # Single account query
                query = query.filter(Account.id == account_id)
                query = query.group_by(Account.id, Account.name)
                results = query.all()
                # Convert Row objects to tuples
                return [(row[0], row[1], row[2], row[3]) for row in results]
            else:
                query = query.group_by(Account.id, Account.name)
                results = query.all()

                # Convert Row objects to tuples
                tuple_results = [(row[0], row[1], row[2], row[3]) for row in results]

                # Always add total row
                if tuple_results:
                    total_orders = sum(row[2] for row in tuple_results)
                    total_paid = sum(row[3] for row in tuple_results)
                    tuple_results.append((None, "TOTAL", total_orders, total_paid))

                return tuple_results

        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error getting order conversation counts by account: {e}")
            raise
