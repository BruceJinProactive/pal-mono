from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, Enum
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import text
from sqlalchemy.types import DateTime, String

from .base import Base
from .types import TargetTier

if TYPE_CHECKING:
    from .agents import Agent
    from .projects import Project
    from .subscriptions import AccountSubscription
    from .users import User


class BusinessIndustry(str, enum.Enum):
    FOOD_BEVERAGE = "food_beverage"
    LIFESTYLE = "lifestyle"
    E_COMMERCE = "e_commerce"


class OnboardingMethod(str, enum.Enum):
    self_onboarding = "self_onboarding"
    manage_onboarding = "manage_onboarding"


class BusinessSegment(str, enum.Enum):
    smb = "smb"  # small & medium business
    mm = "mm"  # mid-market
    ent = "ent"  # enterprise


class AccountStatus(str, enum.Enum):
    pending = "pending"  # initial status, account created but not configured
    initializing = "initializing"  # self-serve onboarding initialization phase
    initialized = "initialized"  # account initialized with basic info
    integration_complete = (
        "integration_complete"  # pos and other third party integration complete
    )
    evaluation_complete = (
        "evaluation_complete"  # agent performance evaluated and ready for production
    )
    active = "active"  # account ready and running in production
    disabled = "disabled"  # temporarily disabled account
    suspended = (
        "suspended"  # account suspended due to payment issues or policy violations
    )
    pending_closure = (
        "pending_closure"  # account closure requested, awaiting final processing
    )
    closed = "closed"  # account closed and no longer accessible
    deleted = (
        "deleted"  # soft delete - account marked as deleted but retained in database
    )


class AccountSegment(str, enum.Enum):
    smb = "smb"  # small & medium business
    mm = "mm"  # mid-market
    ent = "ent"  # enterprise


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
    current_subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    # Owner information
    owner: Mapped[str | None] = mapped_column(String, nullable=True)

    # Business segment and tier information
    segment: Mapped[BusinessSegment | None] = mapped_column(
        Enum(BusinessSegment), nullable=True
    )
    tier: Mapped[TargetTier | None] = mapped_column(Enum(TargetTier), nullable=True)

    # Contract and notes information
    contract_signed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, index=True, server_default=text("false")
    )
    terms_accepted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    terms_envelope_id: Mapped[str | None] = mapped_column(String, nullable=True)
    terms_signed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(String, nullable=True)

    # Contact information
    phone_number: Mapped[str | None] = mapped_column(String, nullable=True)
    channels: Mapped[list[str] | None] = mapped_column(
        ARRAY(String),
        nullable=True,
    )

    # Notification preferences
    notification_preferences: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{\"email_enabled\": true}'::jsonb"),
    )
    notification_email: Mapped[str | None] = mapped_column(String, nullable=True)

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
    subscriptions: Mapped[List["AccountSubscription"]] = relationship(
        "AccountSubscription", back_populates="account"
    )
    onboarding_method: Mapped[OnboardingMethod] = mapped_column(
        Enum(OnboardingMethod),
        nullable=False,
        server_default=OnboardingMethod.manage_onboarding.value,
    )
