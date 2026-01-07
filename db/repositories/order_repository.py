import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import case, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db.tables import Account, Conversation, Message, Project, User
from db.tables.orders import Order
from db.tables.types import IntegrationProvider
from utils.log import logger


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
        Create a new order record.
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
