from __future__ import annotations

import uuid
from datetime import date, datetime, time
from enum import Enum

from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import text
from sqlalchemy.types import Date, DateTime, Integer, String, Text, Time

from .base import Base


class FulfillmentType(str, Enum):
    DELIVERY = "DELIVERY"
    PICKUP = "PICKUP"


class RequestStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class CateringRequest(Base):
    __tablename__ = "catering_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        index=True,
    )
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    event_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    event_address: Mapped[str | None] = mapped_column(String, nullable=True)
    event_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_fulfillment: Mapped[FulfillmentType | None] = mapped_column(
        SQLEnum(FulfillmentType), nullable=True
    )
    contact_name: Mapped[str] = mapped_column(String, nullable=False)
    contact_phone_number: Mapped[str] = mapped_column(String, nullable=False)
    party_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[RequestStatus] = mapped_column(
        SQLEnum(RequestStatus), nullable=False, server_default="PENDING"
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
