"""
Transaction Service

A generic service for managing transaction data across all integration providers.
Provides a standardized way to save, retrieve, and update transaction records
from tools like Adora, Square, Toast, Olo, OpenTable, etc.

"""

from ._implementation import (
    create_transaction,
    get_transaction_by_id,
    update_transaction_status,
    update_transaction_tracking_link,
)
from .schema import OrderTransactionData, TransactionData

__all__ = [
    # Core transaction operations
    "create_transaction",
    "get_transaction_by_id",
    "update_transaction_status",
    "update_transaction_tracking_link",
    # Data schemas
    "TransactionData",
    "OrderTransactionData",
]
