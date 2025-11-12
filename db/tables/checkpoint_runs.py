from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict

from sqlalchemy import Enum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import text
from sqlalchemy.types import Boolean, DateTime, String

from .base import Base
from .types import CheckStatus


class CheckpointRun(Base):
    __tablename__ = "checkpoint_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        index=True,
    )
    checkpoint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    result: Mapped[Dict] = mapped_column(
        MutableDict.as_mutable(JSONB()),
        nullable=True,
        server_default=text("'{}'::jsonb"),
    )
    status: Mapped[CheckStatus] = mapped_column(
        Enum(CheckStatus, name="checkstatus"), nullable=False, index=True
    )
    review: Mapped[str | None] = mapped_column(String, nullable=True)
    reviewer: Mapped[str | None] = mapped_column(String, nullable=True)
    is_reviewed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), index=True
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        onupdate=func.now(),
        server_onupdate=text("now()"),
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        index=True,
    )
