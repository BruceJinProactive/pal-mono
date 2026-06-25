from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class OrderData:
    """Immutable snapshot of an order.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    id: uuid.UUID
    conversation_id: uuid.UUID
    created_at: datetime
    order_id: str | None = None
    store_id: str | None = None
    user_phone_number: str | None = None
    store_phone_number: str | None = None
    tracking_link: str | None = None
    status: str | None = None
    vendor: str | None = None
    subtotal: Decimal | None = None
    order_items: tuple[Any, ...] = ()
    display_payload: dict[str, Any] | None = None
    fulfillment_strategy: str | None = None
    order_time: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "order_items", tuple(self.order_items) if self.order_items else ()
        )


@dataclass(frozen=True)
class LatestOrderData:
    """Lightweight order projection for conversation display lookups."""

    id: uuid.UUID
    conversation_id: uuid.UUID
    created_at: datetime
    order_id: str | None = None


@dataclass(frozen=True)
class OrderCustomerHistoryData:
    """Summary of prior orders for a project/customer phone."""

    order_count: int
    last_order_at: datetime | None = None


@dataclass(frozen=True)
class OrderDetailsData:
    """Order projection for admin console detail lookups."""

    id: uuid.UUID
    conversation_id: uuid.UUID
    created_at: datetime
    order_id: str | None = None
    store_id: str | None = None
    user_phone_number: str | None = None
    store_phone_number: str | None = None
    tracking_link: str | None = None
    status: str | None = None
    vendor: str | None = None
    subtotal: Decimal | None = None
    order_items: tuple[Any, ...] = ()
    display_payload: dict[str, Any] | None = None
    fulfillment_strategy: str | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "order_items", tuple(self.order_items) if self.order_items else ()
        )
