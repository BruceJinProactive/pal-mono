from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import text
from sqlalchemy.types import DateTime, Integer, Text

from .base import Base
from .types import CaptureMode, FeedType, SignalFeedStatus


class SignalFeed(Base):
    __tablename__ = "signal_feeds"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )

    # Reference to source (no FK, managed in code)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    # Feed configuration
    feed_type: Mapped[FeedType] = mapped_column(Enum(FeedType), nullable=False)
    capture_mode: Mapped[CaptureMode] = mapped_column(Enum(CaptureMode), nullable=False)

    # Status
    status: Mapped[SignalFeedStatus] = mapped_column(
        Enum(SignalFeedStatus),
        nullable=False,
        server_default=text("'active'"),
    )
    status_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Capture tracking
    last_capture_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_capture_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    capture_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=func.now()
    )
