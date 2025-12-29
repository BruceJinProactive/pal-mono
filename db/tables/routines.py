from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Enum, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import text
from sqlalchemy.types import Boolean, DateTime, String, Text

from .base import Base
from .types import RoutineCategory


class Routine(Base):
    """Define routine templates that can be scheduled."""

    __tablename__ = "routines"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )

    # Ownership
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    # Identity
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[RoutineCategory] = mapped_column(
        Enum(RoutineCategory),
        nullable=False,
        server_default=text("'custom'"),
    )

    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("project_id", "name", name="routines_project_name_idx"),
    )
