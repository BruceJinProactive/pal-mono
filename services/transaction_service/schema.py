import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, List, Optional

from db.tables.types import IntegrationProvider


@dataclass
class OrderData:
    """
    Standardized order data structure for all tools.

    This class provides a common interface for order data across all
    integration providers (Adora, Square, Toast, Olo, OpenTable, etc.).
    """

    # Required fields
    conversation_id: uuid.UUID
    vendor: IntegrationProvider

    # Optional common fields
    order_id: Optional[str] = None  # Order identifier from external system
    store_id: Optional[str] = None
    tracking_link: Optional[str] = None
    status: Optional[str] = None
    fulfillment_strategy: Optional[str] = None

    # Order-specific fields
    subtotal: Optional[Decimal] = None
    order_items: Optional[List[Any]] = None
    order_time: Optional[datetime] = None

    def __post_init__(self):
        """Validate required fields and set defaults."""
        if not self.conversation_id:
            raise ValueError("conversation_id is required")
        # Ensure order_items is a list
        if self.order_items is None:
            self.order_items = []
