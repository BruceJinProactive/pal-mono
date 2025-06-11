from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Enum, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.expression import text
from sqlalchemy.types import DateTime, String

from .base import Base


class LeadStatus(str, enum.Enum):
    pending = "pending"  # lead just got created and no actions are taken yet
    converted = "converted"  # account created


class BusinessSegment(str, enum.Enum):
    smb = "smb"  # small & medium business
    mm = "mm"  # mid-market
    ent = "ent"  # enterprise


class TargetTier(str, enum.Enum):
    standard = "standard"
    premium = "premium"
    enterprise = "enterprise"


class Lead(Base):
    __tablename__ = "lead"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        index=True,
    )
    # business information
    business_name: Mapped[str | None] = mapped_column(String)
    business_address: Mapped[str | None] = mapped_column(String)
    logo_uri: Mapped[str | None] = mapped_column(String)
    segment: Mapped[BusinessSegment | None] = mapped_column(
        Enum(BusinessSegment), nullable=True
    )
    tier: Mapped[TargetTier | None] = mapped_column(Enum(TargetTier), nullable=True)

    # operational fields
    account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    owner: Mapped[str | None] = mapped_column(String)
    hubspot_record_id: Mapped[str | None] = mapped_column(String)
    status: Mapped[LeadStatus] = mapped_column(
        Enum(LeadStatus), nullable=False, server_default=LeadStatus.pending.value
    )
    notes: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=func.now()
    )
