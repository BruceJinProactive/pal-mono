from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Enum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import text
from sqlalchemy.types import DateTime, Numeric, String

from .base import Base
from .types import IntegrationProvider


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        index=True,
    )
    order_id: Mapped[Optional[str]] = mapped_column(
        String(), nullable=True
    )  # order identifier from external system

    store_id: Mapped[Optional[str]] = mapped_column(String(), nullable=True)
    user_phone_number: Mapped[Optional[str]] = mapped_column(String(), nullable=True)
    store_phone_number: Mapped[Optional[str]] = mapped_column(String(), nullable=True)
    tracking_link: Mapped[Optional[str]] = mapped_column(String(), nullable=True)
    status: Mapped[Optional[str]] = mapped_column(
        String(), nullable=True
    )  # Record the status from the external system

    # Reference identifiers (no foreign key constraints; indexed UUIDs)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    vendor: Mapped[IntegrationProvider | None] = mapped_column(
        Enum(IntegrationProvider),
        nullable=True,
    )

    # Order details
    subtotal: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    order_items: Mapped[Optional[list]] = mapped_column(
        JSONB(),
        nullable=True,
        server_default=text("'[]'::jsonb"),
    )
    fulfillment_strategy: Mapped[Optional[str]] = mapped_column(String(), nullable=True)

    # Timestamps
    order_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # Record the time of the order has been placed
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), index=True
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=func.now()
    )
