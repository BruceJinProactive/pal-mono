from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import text
from sqlalchemy.types import DateTime, String

from .base import Base
from .types import POSProvider


class POSState(str, enum.Enum):
    active = "active"
    inactive = "inactive"


class POSIntegration(Base):
    __tablename__ = "pos_integration"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        index=True,
    )
    store_identifier: Mapped[str] = mapped_column(String, nullable=False)
    provider: Mapped[POSProvider] = mapped_column(Enum(POSProvider), nullable=False)
    state: Mapped[POSState] = mapped_column(Enum(POSState), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    installed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
