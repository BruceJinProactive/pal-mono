import uuid
from typing import Optional

from sqlalchemy.orm import Session

from db.repositories.transaction_repository import TransactionRepository
from db.tables.transactions import Transaction
from utils.log import logger

from .schema import TransactionData


def create_transaction(
    session: Session,
    transaction_data: TransactionData,
    auto_commit: bool = True,
) -> Transaction:
    """
    Create a new transaction record from standardized transaction data.

    Args:
        session: Database session
        transaction_data: Standardized transaction data
        auto_commit: Whether to commit the transaction automatically

    Returns:
        Transaction: The created transaction record

    Raises:
        Exception: If transaction creation fails
    """
    try:
        repository = TransactionRepository(session, auto_commit=auto_commit)

        transaction = repository.create_transaction(
            external_transaction_id=transaction_data.external_transaction_id,
            conversation_id=transaction_data.conversation_id,
            user_id=transaction_data.user_id,
            project_id=transaction_data.project_id,
            vendor=transaction_data.vendor,
            external_transaction_number=transaction_data.external_transaction_number,
            store_id=transaction_data.store_id,
            tracking_link=transaction_data.tracking_link,
            status=transaction_data.status,
            notes=transaction_data.notes,
            subtotal=transaction_data.subtotal,
            order_items=transaction_data.order_items,
            table_size=transaction_data.table_size,
            order_time=transaction_data.order_time,
        )

        logger.info(
            f"[TransactionService] Created transaction {transaction.id} "
            f"for vendor {transaction_data.vendor} with external_id {transaction_data.external_transaction_id}"
        )

        return transaction

    except Exception as e:
        logger.error(
            f"[TransactionService] Failed to create transaction for vendor {transaction_data.vendor}: {e}",
            exc_info=True,
        )
        raise


def get_transaction_by_id(
    session: Session,
    transaction_id: uuid.UUID,
) -> Optional[Transaction]:
    """Get a transaction by its ID."""
    repository = TransactionRepository(session, auto_commit=False)
    return repository.get_transaction_by_id(transaction_id)


def update_transaction_status(
    session: Session,
    transaction_id: uuid.UUID,
    status: str,
    auto_commit: bool = True,
) -> Optional[Transaction]:
    """Update the status of a transaction."""
    repository = TransactionRepository(session, auto_commit=auto_commit)
    return repository.update_transaction_status(transaction_id, status)


def update_transaction_tracking_link(
    session: Session,
    transaction_id: uuid.UUID,
    tracking_link: str,
    auto_commit: bool = True,
) -> Optional[Transaction]:
    """Update the tracking link of a transaction."""
    repository = TransactionRepository(session, auto_commit=auto_commit)
    return repository.update_transaction_tracking_link(transaction_id, tracking_link)
