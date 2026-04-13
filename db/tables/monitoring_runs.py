from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict

from sqlalchemy import Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.expression import text
from sqlalchemy.types import DateTime, Integer, Text

from .base import Base


class MonitoringRun(Base):
    __tablename__ = "monitoring_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )

    monitoring_config_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )

    # Metadata
    trigger_metadata: Mapped[Dict] = mapped_column(
        MutableDict.as_mutable(JSONB()),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    # Execution Timing
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Results
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evaluation_result: Mapped[Dict] = mapped_column(
        MutableDict.as_mutable(JSONB()),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    # Error Handling
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index(
            "ix_monitoring_runs_config_started",
            "monitoring_config_id",
            text("started_at DESC"),
        ),
        Index("ix_monitoring_runs_result", "result"),
        Index("ix_monitoring_runs_started_at", text("started_at DESC")),
    )
