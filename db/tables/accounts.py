from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import text
from sqlalchemy.types import DateTime, String

from .base import Base

if TYPE_CHECKING:
    from .agents import Agent
    from .projects import Project
    from .users import User


class BusinessIndustry(str, enum.Enum):
    FOOD_BEVERAGE = "food_beverage"
    LIFESTYLE = "lifestyle"
    E_COMMERCE = "e_commerce"


class AccountStatus(str, enum.Enum):
    active = "active"  # account in operation
    pending = "pending"  # account created but not activated
    initializing = "initializing"  # activated but not fully onboarded
    disabled = "disabled"  # temporarily disabled account
    deleted = "deleted"  # soft deleting account


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
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    icon_uri: Mapped[str | None] = mapped_column(String, nullable=True)

    # Attributes that provide basic context for the business account
    industry: Mapped[BusinessIndustry | None] = mapped_column(String, nullable=True)
    business_description: Mapped[str | None] = mapped_column(String, nullable=True)
    business_faq: Mapped[str | None] = mapped_column(String, nullable=True)
    business_promotions: Mapped[str | None] = mapped_column(String, nullable=True)
    business_catalog: Mapped[str | None] = mapped_column(String, nullable=True)
    business_others: Mapped[str | None] = mapped_column(String, nullable=True)

    # Stripe subscription info
    stripe_customer_id: Mapped[str | None] = mapped_column(String, nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String, nullable=True)

    # Metadata columns
    status: Mapped[AccountStatus] = mapped_column(
        Enum(AccountStatus), nullable=False, server_default=AccountStatus.active.value
    )
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
    agents: Mapped[List["Agent"]] = relationship("Agent", back_populates="account")
    users: Mapped[List["User"]] = relationship("User", back_populates="account")
