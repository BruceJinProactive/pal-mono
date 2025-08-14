import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db.tables import Conversation, Message, Project, User
from db.tables.transactions import Transaction
from db.tables.types import IntegrationProvider, IntegrationType
from utils.log import logger


class TransactionRepository:
    """Repository for managing transaction database operations."""

    def __init__(self, session: Session, auto_commit: bool = True):
        self.session = session
        self.auto_commit = auto_commit

    def create_transaction(
        self,
        external_transaction_id: str,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        vendor: Optional[IntegrationProvider] = None,
        external_transaction_number: Optional[str] = None,
        store_id: Optional[str] = None,
        tracking_link: Optional[str] = None,
        status: Optional[str] = None,
        integration_type: Optional[IntegrationType] = None,
        fulfillment_strategy: Optional[str] = None,
        notes: Optional[str] = None,
        subtotal: Optional[Decimal] = None,
        order_items: Optional[list] = None,
        table_size: Optional[int] = None,
        order_time: Optional[datetime] = None,
    ) -> Transaction:
        """
        Create a new transaction record.
        Args:
            external_transaction_id: The ID from the external system (required)
            conversation_id: The conversation this transaction belongs to (required)
            user_id: The user who created this transaction (required)
            project_id: The project this transaction belongs to (required)
            vendor: The integration provider/vendor (required)
            external_transaction_number: Human-readable transaction number from external system
            store_id: Store/location identifier
            tracking_link: Link to track the order/reservation
            status: Current status of the transaction
            integration_type: Type of integration (pos, loyalty, reservation)
            fulfillment_strategy: Strategy for fulfilling the transaction
            notes: Additional notes about the transaction
            subtotal: Transaction subtotal amount
            order_items: List of items in the order (for orders)
            table_size: Number of people (for reservations)
            order_time: When the order/reservation was placed
        Returns:
            Transaction: The created transaction record
        """
        transaction = Transaction(
            external_transaction_id=external_transaction_id,
            external_transaction_number=external_transaction_number,
            store_id=store_id,
            tracking_link=tracking_link,
            status=status,
            integration_type=integration_type,
            fulfillment_strategy=fulfillment_strategy,
            conversation_id=conversation_id,
            user_id=user_id,
            project_id=project_id,
            vendor=vendor,
            notes=notes,
            subtotal=subtotal,
            order_items=order_items or [],
            table_size=table_size,
            order_time=order_time,
        )
        self.session.add(transaction)
        if self.auto_commit:
            self.session.commit()
        return transaction

    def get_transaction_by_id(self, transaction_id: uuid.UUID) -> Optional[Transaction]:
        """Get a transaction by its ID."""
        return (
            self.session.query(Transaction)
            .filter(Transaction.id == transaction_id)
            .first()
        )

    def update_transaction_status(
        self, transaction_id: uuid.UUID, status: str
    ) -> Optional[Transaction]:
        """Update the status of a transaction."""
        transaction = self.get_transaction_by_id(transaction_id)
        if transaction:
            transaction.status = status
            if self.auto_commit:
                self.session.commit()
        return transaction

    def update_transaction_tracking_link(
        self, transaction_id: uuid.UUID, tracking_link: str
    ) -> Optional[Transaction]:
        """Update the tracking link of a transaction."""
        transaction = self.get_transaction_by_id(transaction_id)
        if transaction:
            transaction.tracking_link = tracking_link
            if self.auto_commit:
                self.session.commit()
        return transaction

    def get_order_value(
        self,
        account_id: uuid.UUID,
        start_date: datetime,
        end_date: datetime,
    ):
        """
        Calculate order totals for a given account within a date range,
        grouped by channel and project. Only includes completed POS orders.
        Args:
            account_id (uuid.UUID): The account ID to filter transactions by
            start_date (datetime): Start date for the calculation
            end_date (datetime): End date for the calculation
        Returns:
            list: Raw query results with date, channel, project_id, and "Order Total" fields.
        """
        try:
            # Define expressions for efficient querying
            date_expr = func.date(Transaction.order_time)
            channel_expr = Message.body["channel"].astext
            # Query to get order totals by joining transactions -> conversations -> messages
            # Group by date, channel, and project
            # Only include completed POS orders
            query = (
                select(
                    date_expr.label("date"),
                    channel_expr.label("channel"),
                    Transaction.project_id.label("project_id"),
                    Project.name.label("project_name"),
                    func.coalesce(func.sum(Transaction.subtotal), 0).label(
                        "order_total"
                    ),
                )
                .join(Conversation, Transaction.conversation_id == Conversation.id)
                .join(Message, Conversation.id == Message.conversation_id)
                .join(User, Conversation.user_id == User.id)
                .join(Project, Transaction.project_id == Project.id)
                .filter(
                    User.account_id == account_id,
                    Transaction.order_time >= start_date,
                    Transaction.order_time <= end_date,
                    Transaction.subtotal.isnot(
                        None
                    ),  # Only include transactions with subtotals
                    Transaction.integration_type
                    == IntegrationType.pos,  # Only POS transactions
                    Transaction.status != "pending",  # Exclude pending orders
                )
                .group_by(date_expr, channel_expr, Transaction.project_id, Project.name)
                .order_by(date_expr, channel_expr, Transaction.project_id)
            )
            result = self.session.execute(query)
            rows = result.all()
            return rows
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error calculating order values: {e}")
            return []
