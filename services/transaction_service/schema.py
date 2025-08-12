import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, List, Optional

from db.tables.types import IntegrationProvider, IntegrationType


@dataclass
class TransactionData:
    """
    Standardized transaction data structure for all tools.

    This class provides a common interface for transaction data across all
    integration providers (Adora, Square, Toast, Olo, OpenTable, etc.).
    """

    # Required fields
    external_transaction_id: (
        str  # ID from external system (order_id, reservation_id, etc.)
    )
    conversation_id: uuid.UUID
    user_id: uuid.UUID
    project_id: uuid.UUID
    vendor: IntegrationProvider

    # Optional common fields
    external_transaction_number: Optional[str] = None  # Human-readable number
    store_id: Optional[str] = None
    tracking_link: Optional[str] = None
    status: Optional[str] = None
    integration_type: Optional[IntegrationType] = None
    fulfillment_strategy: Optional[str] = None
    notes: Optional[str] = None

    # Order-specific fields
    subtotal: Optional[Decimal] = None
    order_items: Optional[List[Any]] = None
    order_time: Optional[datetime] = None
    table_size: Optional[int] = None

    def __post_init__(self):
        """Validate required fields and set defaults."""
        if not self.external_transaction_id:
            raise ValueError("external_transaction_id is required")
        if not self.conversation_id:
            raise ValueError("conversation_id is required")
        if not self.user_id:
            raise ValueError("user_id is required")
        if not self.project_id:
            raise ValueError("project_id is required")


@dataclass
class OrderTransactionData(TransactionData):
    """Specialized transaction data for order-based transactions."""

    def __post_init__(self):
        super().__post_init__()
        # Ensure order_items is a list
        if self.order_items is None:
            self.order_items = []
