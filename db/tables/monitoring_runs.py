from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict

from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.expression import text
from sqlalchemy.types import DateTime, Text

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
    evaluation_result: Mapped[Dict] = mapped_column(
        MutableDict.as_mutable(JSONB()),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    # Error Handling
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
