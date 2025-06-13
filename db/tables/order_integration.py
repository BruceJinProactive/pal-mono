from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import text
from sqlalchemy.types import DateTime, String

from .base import Base
from .types import OrderIntegrationVendor


class OrderProtocol(str, enum.Enum):
    SMS = "sms"
    POS = "pos"


class OrderIntegration(Base):
    __tablename__ = "order_integration"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        index=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    protocol: Mapped[OrderProtocol] = mapped_column(Enum(OrderProtocol), nullable=False)
    vendor: Mapped[OrderIntegrationVendor | None] = mapped_column(
        Enum(OrderIntegrationVendor), nullable=True
    )
    destination: Mapped[str] = mapped_column(String, nullable=False)

    # Metadata columns
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=func.now()
    )
