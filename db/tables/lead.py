from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import ARRAY, Boolean, Enum, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.expression import text
from sqlalchemy.types import DateTime, String

from .base import Base
from .types import TargetTier


class LeadStatus(str, enum.Enum):
    pending = "pending"  # lead just got created and no actions are taken yet
    account_created = "account_created"  # account created
    integration_ready = (
        "integration_ready"  # account created & pos integration complete
    )
    in_operation = "in_operation"  # agent serving real customers


class BusinessSegment(str, enum.Enum):
    smb = "smb"  # small & medium business
    mm = "mm"  # mid-market
    ent = "ent"  # enterprise


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
    pos: Mapped[str | None] = mapped_column(String)
    channels: Mapped[list[str] | None] = mapped_column(
        ARRAY(String),
        nullable=True,
    )
    # operational fields
    account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    owner: Mapped[str | None] = mapped_column(String)
    hubspot_record_id: Mapped[str | None] = mapped_column(String)
    status: Mapped[LeadStatus] = mapped_column(
        Enum(LeadStatus), nullable=False, server_default=LeadStatus.pending.value
    )
    contract_signed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, index=True, server_default=text("false")
    )
    notes: Mapped[str | None] = mapped_column(String)

    deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, index=True, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=func.now()
    )
