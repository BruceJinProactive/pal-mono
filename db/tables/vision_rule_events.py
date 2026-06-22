from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Dict

from sqlalchemy import Index, PrimaryKeyConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.expression import text
from sqlalchemy.types import Boolean, DateTime, Numeric, String

from .base import Base


class VisionRuleEvent(Base):
    __tablename__ = "vision_rule_event"
    __table_args__ = (
        PrimaryKeyConstraint("id", "triggered_at"),
        Index("idx_vre_rule_time", "rule_id", "triggered_at", postgresql_using="btree"),
        Index(
            "idx_vre_entity_time",
            "entity_id",
            "triggered_at",
            postgresql_using="btree",
        ),
        Index("idx_vre_triggered", "triggered_at", postgresql_using="btree"),
        {"postgresql_partition_by": "RANGE (triggered_at)"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
        nullable=False,
    )

    rule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    state_change_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )

    severity: Mapped[str] = mapped_column(String(20), nullable=False)

    duration: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False, server_default=text("0.0")
    )

    manually_adjusted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    event_metadata: Mapped[Dict] = mapped_column(
        MutableDict.as_mutable(JSONB()),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
