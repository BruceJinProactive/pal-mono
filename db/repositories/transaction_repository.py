import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from db.tables.transactions import Transaction
from db.tables.types import IntegrationProvider


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
        vendor: IntegrationProvider,
        external_transaction_number: Optional[str] = None,
        store_id: Optional[str] = None,
        tracking_link: Optional[str] = None,
        status: Optional[str] = None,
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
