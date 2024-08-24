from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import text
from sqlalchemy.types import DateTime, String

from db.tables.base import Base

if TYPE_CHECKING:
    from db.tables.assistants import Assistant
    from db.tables.projects import Project
    from db.tables.users import User


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)

    # Metadata columns
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=func.now()
    )

    # Relationships
    projects: Mapped[List["Project"]] = relationship(
        "Project", back_populates="account"
    )
    assistants: Mapped[List["Assistant"]] = relationship(
        "Assistant", back_populates="account"
    )
    users: Mapped[List["User"]] = relationship("User", back_populates="account")
