from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional

from sqlalchemy import Enum, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import text
from sqlalchemy.types import Boolean, DateTime, Numeric, String, Text

from .base import Base
from .types import ItemResponseStatus


class RoutineItemResponse(Base):
    """Store evidence for each item in a submission."""

    __tablename__ = "routine_item_responses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )

    # Parents
    submission_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    routine_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )

    # Response data (V1: photo only)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # AI verification results
    ai_result: Mapped[Dict | None] = mapped_column(
        MutableDict.as_mutable(JSONB()),
        nullable=True,
    )
    ai_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ai_confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)

    # Status
    status: Mapped[ItemResponseStatus] = mapped_column(
        Enum(ItemResponseStatus),
        nullable=False,
        server_default=text("'pending'"),
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "submission_id",
            "routine_item_id",
            name="routine_item_responses_unique_idx",
        ),
    )
