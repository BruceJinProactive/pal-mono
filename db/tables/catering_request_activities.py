from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Enum, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.expression import text
from sqlalchemy.types import DateTime, Integer, String, Text

from .base import Base


class CateringRequestActivityType(str, enum.Enum):
    REQUEST_CREATED = "REQUEST_CREATED"
    REQUEST_UPDATED = "REQUEST_UPDATED"
    STATUS_CHANGED = "STATUS_CHANGED"
    ACTION_ITEM_COMPLETED = "ACTION_ITEM_COMPLETED"
    ACTION_ITEM_REOPENED = "ACTION_ITEM_REOPENED"
    PROPOSAL_CREATED = "PROPOSAL_CREATED"
    PROPOSAL_SENT = "PROPOSAL_SENT"
    PROPOSAL_APPROVED = "PROPOSAL_APPROVED"
    SMS_SENT = "SMS_SENT"
    SMS_RECEIVED = "SMS_RECEIVED"
    PAYMENT_RECEIVED = "PAYMENT_RECEIVED"
    NOTE_ADDED = "NOTE_ADDED"
    DEADLINE_SCHEDULED = "DEADLINE_SCHEDULED"
    ORDER_LOCKED = "ORDER_LOCKED"
    TOAST_ORDER_CREATED = "TOAST_ORDER_CREATED"


class CateringRequestActivityActorType(str, enum.Enum):
    CUSTOMER = "CUSTOMER"
    CATERING_MANAGER = "CATERING_MANAGER"
    INTERNAL_USER = "INTERNAL_USER"
    SYSTEM = "SYSTEM"
    AI_AGENT = "AI_AGENT"
    INTEGRATION = "INTEGRATION"


class CateringRequestActivitySource(str, enum.Enum):
    ADMIN_CONSOLE = "ADMIN_CONSOLE"
    CUSTOMER_EMAIL = "CUSTOMER_EMAIL"
    CUSTOMER_SMS = "CUSTOMER_SMS"
    CUSTOMER_VOICE = "CUSTOMER_VOICE"
    INTERNAL_APP = "INTERNAL_APP"
    SYSTEM_JOB = "SYSTEM_JOB"
    AI_AGENT = "AI_AGENT"
    TOAST = "TOAST"
    API = "API"


class CateringRequestActivity(Base):
    __tablename__ = "catering_request_activities"
    __table_args__ = (
        Index(
            "idx_catering_request_activities_request_time",
            "catering_request_id",
            "occurred_at",
        ),
        Index(
            "idx_catering_request_activities_project_time",
            "project_id",
            "occurred_at",
        ),
        Index(
            "idx_catering_request_activities_actor",
            "actor_type",
            "actor_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
        nullable=False,
        index=True,
    )
    catering_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    activity_type: Mapped[CateringRequestActivityType] = mapped_column(
        Enum(CateringRequestActivityType), nullable=False
    )
    actor_type: Mapped[CateringRequestActivityActorType] = mapped_column(
        Enum(CateringRequestActivityActorType), nullable=False
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    actor_display_name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    activity_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        MutableDict.as_mutable(JSONB()),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    source: Mapped[CateringRequestActivitySource] = mapped_column(
        Enum(CateringRequestActivitySource), nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
