from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import text
from sqlalchemy.types import DateTime, Integer, String

from .base import Base
from .types import IntegrationProvider


class Reservation(Base):
    __tablename__ = "reservations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        index=True,
    )
    reservation_id: Mapped[Optional[str]] = mapped_column(
        String(), nullable=True
    )  # reservation identifier from external system
    store_id: Mapped[Optional[str]] = mapped_column(String(), nullable=True)
    tracking_link: Mapped[Optional[str]] = mapped_column(String(), nullable=True)

    status: Mapped[Optional[str]] = mapped_column(
        String(), nullable=True
    )  # Record the status from the external system

    # Reference identifiers (no foreign key constraints; indexed UUIDs)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    vendor: Mapped[IntegrationProvider | None] = mapped_column(
        Enum(IntegrationProvider),
        nullable=True,
    )

    # Reservation details
    table_size: Mapped[Optional[int]] = mapped_column(Integer(), nullable=True)
    special_requests: Mapped[Optional[str]] = mapped_column(String(), nullable=True)

    # Entry type discriminator (reservation vs waitlist)
    entry_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'reservation'"),
        index=True,  # For analytics filtering by entry type
    )

    # Waitlist-specific timestamps (from external APIs like Yelp)
    arrive_by_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # When customer should arrive (Yelp provides this)

    expected_seating_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # Estimated seating time (Yelp provides this)

    # Timestamps
    reservation_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # Record the time of the reservation
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=func.now()
    )
