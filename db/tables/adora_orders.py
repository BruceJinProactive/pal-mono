from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import text
from sqlalchemy.types import DateTime, String

from .base import Base
from .types import IntegrationProvider


class AdoraOrder(Base):
    __tablename__ = "adora_orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        index=True,
    )

    # Order details
    user_phone_number: Mapped[str] = mapped_column(String(), nullable=False)
    store_phone_number: Mapped[str] = mapped_column(String(), nullable=False)
    order_number: Mapped[str] = mapped_column(String(), nullable=False)
    transaction_id: Mapped[str] = mapped_column(String(), nullable=False)
    store_id: Mapped[str] = mapped_column(String(), nullable=False)
    tracking_link: Mapped[Optional[str]] = mapped_column(String(), nullable=True)
    status: Mapped[str] = mapped_column(String(), nullable=False)

    # Integration details
    vendor: Mapped[IntegrationProvider | None] = mapped_column(
        Enum(
            IntegrationProvider,
        ),
        nullable=True,
    )

    # Timestamps
    order_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=func.now()
    )

    __table_args__ = (
        # Ensure order_number is unique per store
        UniqueConstraint("store_id", "order_number", name="uq_store_order"),
    )
