from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import List, Optional

from sqlalchemy import Enum
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import text
from sqlalchemy.types import Boolean, Date, DateTime, Integer, String, Time

from .base import Base
from .types import RoutineFrequency


class RoutineSchedule(Base):
    """Define when routines should be completed."""

    __tablename__ = "routine_schedules"

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

    # Schedule definition
    frequency: Mapped[RoutineFrequency] = mapped_column(
        Enum(RoutineFrequency),
        nullable=False,
    )
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    timezone: Mapped[str] = mapped_column(
        String(100), nullable=False, server_default=text("'America/Los_Angeles'")
    )

    # Frequency-specific
    days_of_week: Mapped[List[int] | None] = mapped_column(
        ARRAY(Integer), nullable=True
    )
    day_of_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    interval_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Date range
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_until: Mapped[date | None] = mapped_column(Date, nullable=True)

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
