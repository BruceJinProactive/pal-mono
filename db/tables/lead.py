from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.expression import text
from sqlalchemy.types import DateTime, String

from .base import Base


class Lead(Base):
    __tablename__ = "lead"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        index=True,
    )
    business_name: Mapped[str | None] = mapped_column(String)
    business_address: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
