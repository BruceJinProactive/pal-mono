from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Enum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import text
from sqlalchemy.types import DateTime, Integer, Numeric, String

from .base import Base
from .types import IntegrationProvider

if TYPE_CHECKING:
    pass


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        index=True,
    )
    external_transaction_id: Mapped[str] = mapped_column(
        String(), nullable=False
    )  # reservation_id / transaction_id
    external_transaction_number: Mapped[Optional[str]] = mapped_column(
        String(), nullable=True
    )  # reservation_number / transaction_number

    store_id: Mapped[Optional[str]] = mapped_column(String(), nullable=True)
    tracking_link: Mapped[Optional[str]] = mapped_column(String(), nullable=True)
    status: Mapped[Optional[str]] = mapped_column(
        String(), nullable=True
    )  # Record the status from the external system

    # Reference identifiers (no foreign key constraints; indexed UUIDs)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    vendor: Mapped[IntegrationProvider | None] = mapped_column(
        Enum(IntegrationProvider),
        nullable=True,
    )

    notes: Mapped[Optional[str]] = mapped_column(String(), nullable=True)

    # Transaction details
    subtotal: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    order_items: Mapped[Optional[list]] = mapped_column(
        JSONB(),
        nullable=True,
        server_default=text("'[]'::jsonb"),
    )

    # Reservation details
    table_size: Mapped[Optional[int]] = mapped_column(Integer(), nullable=True)

    # Timestamps
    order_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # Record the time of the order has been placed or reservation has been made
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=func.now()
    )
