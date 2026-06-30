from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import text
from sqlalchemy.types import Boolean, DateTime, Integer, String, Text

from .base import Base


class VisionCameraConfiguration(Base):
    __tablename__ = "vision_camera_configuration"
    __table_args__ = (UniqueConstraint("signal_source_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )

    signal_source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    llm_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    llm_provider: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'azure'")
    )
    llm_model: Mapped[str] = mapped_column(
        String(100), nullable=False, server_default=text("'gpt-4o'")
    )

    processing_interval_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("15")
    )

    reference_images: Mapped[List] = mapped_column(
        MutableList.as_mutable(JSONB()),
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )

    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    structured_observations_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=func.now()
    )
