from __future__ import annotations

import uuid
from datetime import datetime, time
from typing import List, Optional

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import text
from sqlalchemy.types import Boolean, DateTime, Integer, String, Text, Time

from .base import Base


class VisionCameraConfiguration(Base):
    __tablename__ = "vision_camera_configuration"
    __table_args__ = (
        UniqueConstraint("signal_source_id"),
        CheckConstraint(
            "check_mode IN ('none', 'daily', 'weekly')",
            name="ck_vision_camera_configuration_check_mode_valid",
        ),
        CheckConstraint(
            "check_mode = 'none' OR "
            "(check_start_time IS NOT NULL AND check_end_time IS NOT NULL)",
            name="ck_vision_camera_configuration_check_window_required",
        ),
        CheckConstraint(
            "check_frequency_minutes > 0",
            name="ck_vision_camera_configuration_check_frequency_minutes_positive",
        ),
        CheckConstraint(
            "weekly_observation_days <@ ARRAY["
            "'monday', 'tuesday', 'wednesday', 'thursday', "
            "'friday', 'saturday', 'sunday'"
            "]::varchar[]",
            name="ck_vision_camera_configuration_weekly_observation_days_valid",
        ),
        CheckConstraint(
            "cardinality(weekly_observation_days) > 0",
            name="ck_vision_camera_configuration_weekly_observation_days_nonempty",
        ),
    )

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

    check_mode: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default=text("'daily'")
    )

    check_start_time: Mapped[Optional[time]] = mapped_column(
        Time(timezone=False), nullable=True, server_default=text("'00:00:00'")
    )

    check_end_time: Mapped[Optional[time]] = mapped_column(
        Time(timezone=False), nullable=True, server_default=text("'23:59:59.999999'")
    )

    check_frequency_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )

    weekly_observation_days: Mapped[list[str]] = mapped_column(
        ARRAY(String(9)),
        nullable=False,
        server_default=text(
            "ARRAY["
            "'monday', 'tuesday', 'wednesday', 'thursday', "
            "'friday', 'saturday', 'sunday'"
            "]::varchar[]"
        ),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=func.now()
    )
