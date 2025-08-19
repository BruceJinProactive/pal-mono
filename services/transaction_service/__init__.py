"""
Transaction Service

A generic service for managing transaction data across all integration providers.
Provides a standardized way to save, retrieve, and update transaction records
from tools like Adora, Square, Toast, Olo, OpenTable, etc.
"""

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from db.tables.transactions import Transaction
from db.tables.types import IntegrationProvider

from . import _implementation
from ._utils import (
    reconstruct_order_items,
    save_transaction,
    update_transaction_by_order_number_helper,
)
from .schema import OrderTransactionData, TransactionData


def create_transaction(
    session: Session,
    transaction_data: TransactionData,
) -> Transaction:
    """
    Create a new transaction record from standardized transaction data.

    Args:
        session: Database session
        transaction_data: Standardized transaction data

    Returns:
        Transaction: The created transaction record
    """
    return _implementation.create_transaction(session, transaction_data)


def get_transaction_by_id(
    session: Session,
    transaction_id: uuid.UUID,
) -> Optional[Transaction]:
    """
    Get a transaction by its ID.

    Args:
        session: Database session
        transaction_id: The ID of the transaction to retrieve

    Returns:
        Transaction | None: The transaction if found, None otherwise
    """
    return _implementation.get_transaction_by_id(session, transaction_id)


def update_transaction_by_order_number(
    session: Session,
    store_id: str,
    vendor: IntegrationProvider,
    external_transaction_number: str,
    **kwargs,
) -> Optional[Transaction]:
    """
    Update a transaction by its external transaction number, store ID, and vendor.

    Args:
        session: Database session
        store_id: The store ID to find
        vendor: The integration provider (adora, square, toast, etc.)
        external_transaction_number: The external order number to find
        **kwargs: Fields to update (status, tracking_link, notes, etc.)

    Returns:
        Transaction | None: The updated transaction if found, None otherwise
    """
    return _implementation.update_transaction_by_order_number(
        session, store_id, vendor, external_transaction_number, **kwargs
    )


__all__ = [
    # Core transaction operations
    "create_transaction",
    "get_transaction_by_id",
    "update_transaction_by_order_number",
    # Helper functions for tools
    "save_transaction",
    "update_transaction_by_order_number_helper",
    "reconstruct_order_items",
    # Data schemas
    "TransactionData",
    "OrderTransactionData",
]
