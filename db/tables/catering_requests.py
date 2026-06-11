from __future__ import annotations

import uuid
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum

from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import text
from sqlalchemy.types import Date, DateTime, Integer, Numeric, String, Text, Time

from .base import Base


class FulfillmentType(str, Enum):
    DELIVERY = "DELIVERY"
    PICKUP = "PICKUP"


class RequestStatus(str, Enum):
    LEAD = "LEAD"
    PROPOSAL = "PROPOSAL"
    LOCKED = "LOCKED"
    IN_PREPARATION = "IN_PREPARATION"
    CLOSED = "CLOSED"
    INQUIRY = "INQUIRY"
    QUOTE_SENT = "QUOTE_SENT"
    CONFIRMED = "CONFIRMED"
    IN_PREP = "IN_PREP"
    READY = "READY"
    FULFILLED = "FULFILLED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    ISSUE = "ISSUE"
    # Backward-compatible aliases for in-flight code paths.
    PENDING = INQUIRY


class CateringRequest(Base):
    __tablename__ = "catering_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        index=True,
    )
    event_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    event_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    event_address: Mapped[str | None] = mapped_column(String, nullable=True)
    event_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    all_items: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    event_fulfillment: Mapped[FulfillmentType | None] = mapped_column(
        SQLEnum(FulfillmentType), nullable=True
    )
    contact_name: Mapped[str] = mapped_column(String, nullable=False)
    contact_phone_number: Mapped[str | None] = mapped_column(String, nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String, nullable=True)
    party_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prior_catering_request_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    prior_order_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    last_catering_request_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_order_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    estimated_order_value: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    confirmed_order_value: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    deposit_requirement_value: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    deposit_received_value: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    status: Mapped[RequestStatus] = mapped_column(
        SQLEnum(RequestStatus), nullable=False, server_default="INQUIRY"
    )

    # Idempotency key for preventing duplicate requests
    idempotency_key: Mapped[str] = mapped_column(
        String, nullable=False, unique=True, server_default=func.gen_random_uuid()
    )

    # Reference IDs (no foreign key constraints - handled at app level)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )

    # Metadata columns
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=func.now()
    )
