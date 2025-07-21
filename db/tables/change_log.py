from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import List

from sqlalchemy import Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql.expression import text
from sqlalchemy.types import DateTime, String

from .base import Base


class ChangeResourceType(str, enum.Enum):
    Account = "Account"
    Agent = "Agent"
    Project = "Project"
    OrderIntegration = "OrderIntegration"
    POSIntegration = "POSIntegration"
    SubscriptionPlan = "SubscriptionPlan"
    Subscription = "Subscription"
    Prompt = "Prompt"


class ChangeAction(str, enum.Enum):
    Update = "Update"
    Create = "Create"
    Delete = "Delete"


class ChangeLog(Base):
    __tablename__ = "change_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        index=True,
    )
    resource_type: Mapped[ChangeResourceType] = mapped_column(
        Enum(ChangeResourceType), nullable=False
    )
    resource_id: Mapped[str] = mapped_column(String, nullable=False)
    author: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[ChangeAction] = mapped_column(Enum(ChangeAction), nullable=False)

    # Metadata columns
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    # Relationships
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    fields: Mapped[List["ChangeField"]] = relationship(
        "ChangeField", back_populates="change_log"
    )


class ChangeField(Base):
    __tablename__ = "change_field"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        index=True,
    )
    field: Mapped[str] = mapped_column(String, nullable=False)
    old_value: Mapped[str] = mapped_column(String, nullable=True)
    new_value: Mapped[str] = mapped_column(String, nullable=True)

    # Relationships
    change_log_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("change_log.id"), nullable=False, index=True
    )
    change_log: Mapped["ChangeLog"] = relationship("ChangeLog", back_populates="fields")
