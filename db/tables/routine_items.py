from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import Enum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import text
from sqlalchemy.types import Boolean, DateTime, Integer, String, Text

from .base import Base
from .types import RoutineInputType


class RoutineItem(Base):
    """Define individual tasks within a routine."""

    __tablename__ = "routine_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )

    # Parent
    routine_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    # Identity
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )

    # Input configuration
    input_type: Mapped[RoutineInputType] = mapped_column(
        Enum(RoutineInputType),
        nullable=False,
        server_default=text("'photo'"),
    )
    is_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )

    # AI verification (for photo type)
    reference_images: Mapped[list[dict[str, Any]]] = mapped_column(
        MutableList.as_mutable(JSONB()),
        nullable=False,
        server_default=text("'[]'::jsonb"),
        comment="List of dicts with 'image_url' and 'description' fields",
    )
    ai_rules: Mapped[Dict] = mapped_column(
        MutableDict.as_mutable(JSONB()),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    # Camera integration (optional)
    signal_source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=func.now()
    )
