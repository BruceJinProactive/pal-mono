import uuid
from typing import Optional

from sqlalchemy.orm import Session

from db.repositories.transaction_repository import TransactionRepository
from db.tables.transactions import Transaction
from db.tables.types import IntegrationProvider

from .schema import TransactionData


def create_transaction(
    session: Session,
    transaction_data: TransactionData,
) -> Transaction:
    """Create a new transaction record from standardized transaction data."""
    repository = TransactionRepository(session, auto_commit=True)
    return repository.create_transaction(
        external_transaction_id=transaction_data.external_transaction_id,
        conversation_id=transaction_data.conversation_id,
        user_id=transaction_data.user_id,
        project_id=transaction_data.project_id,
        vendor=transaction_data.vendor,
        external_transaction_number=transaction_data.external_transaction_number,
        store_id=transaction_data.store_id,
        tracking_link=transaction_data.tracking_link,
        status=transaction_data.status,
        integration_type=transaction_data.integration_type,
        fulfillment_strategy=transaction_data.fulfillment_strategy,
        notes=transaction_data.notes,
        subtotal=transaction_data.subtotal,
        order_items=transaction_data.order_items,
        table_size=transaction_data.table_size,
        order_time=transaction_data.order_time,
    )


def get_transaction_by_id(
    session: Session,
    transaction_id: uuid.UUID,
) -> Optional[Transaction]:
    """Get a transaction by its ID."""
    repository = TransactionRepository(session, auto_commit=False)
    return repository.get_transaction_by_id(transaction_id)


def update_transaction_by_order_number(
    session: Session,
    store_id: str,
    vendor: IntegrationProvider,
    external_transaction_number: str,
    **kwargs,
) -> Optional[Transaction]:
    """Update a transaction by its external transaction number, store ID, and vendor."""
    repository = TransactionRepository(session, auto_commit=True)
    return repository.update_transaction_by_order_number(
        store_id=store_id,
        vendor=vendor,
        external_transaction_number=external_transaction_number,
        **kwargs,
    )
