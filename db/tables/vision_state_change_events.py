from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict, Optional

from sqlalchemy import Index, PrimaryKeyConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.expression import text
from sqlalchemy.types import DateTime, Float, String

from .base import Base


class VisionStateChangeEvent(Base):
    __tablename__ = "vision_state_change_event"
    __table_args__ = (
        PrimaryKeyConstraint("id", "observed_at"),
        Index(
            "idx_sce_entity_time", "entity_id", "observed_at", postgresql_using="btree"
        ),
        Index("idx_sce_observed", "observed_at", postgresql_using="btree"),
        {"postgresql_partition_by": "RANGE (observed_at)"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
        nullable=False,
    )

    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    camera_config_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    previous_state_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    new_state_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    frame_s3_key: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    event_metadata: Mapped[Dict] = mapped_column(
        "metadata",
        MutableDict.as_mutable(JSONB()),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
