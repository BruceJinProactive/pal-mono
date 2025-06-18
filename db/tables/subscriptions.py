from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import ForeignKey
from sqlalchemy.sql.expression import text
from sqlalchemy.types import Boolean, DateTime, Enum, Integer, String

from .base import Base
from .types import SubscriptionStatus, SubscriptionType, TargetTier

if TYPE_CHECKING:
    from .accounts import Account


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    tier: Mapped[TargetTier] = mapped_column(
        Enum(TargetTier, name="targettier", native_enum=False), nullable=False
    )
    features_included: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=True, server_default=text("'{}'")
    )
    features_excluded: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=True, server_default=text("'{}'")
    )
    call_quota: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    order_quota: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    call_overage_charge: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    order_overage_charge: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    free_trial_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    monthly_fee: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    stripe_price_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    sort_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )


class AccountSubscription(Base):
    __tablename__ = "account_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        index=True,
    )
    external_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        unique=True,
        index=True,
    )
    version: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, default=1, server_default="1"
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True
    )
    subscription_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subscription_plans.id"),
        nullable=False,
        index=True,
    )
    subscription_type: Mapped[SubscriptionType] = mapped_column(
        Enum(SubscriptionType, name="subscriptiontype", native_enum=False),
        nullable=False,
    )
    start_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    call_quota: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    order_quota: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    call_overage_charge: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    order_overage_charge: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    monthly_fee: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(
        String, nullable=True, index=True
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, name="subscriptionstatus", native_enum=False),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )

    account: Mapped["Account"] = relationship("Account", back_populates="subscriptions")
    subscription_plan: Mapped["SubscriptionPlan"] = relationship("SubscriptionPlan")
