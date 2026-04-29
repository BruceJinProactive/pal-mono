from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Index, and_
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import ForeignKey
from sqlalchemy.sql.expression import text
from sqlalchemy.types import Boolean, DateTime, Enum, Float, Integer, String

from .base import Base
from .types import (
    PaymentMethod,
    RecurringCreditFrequency,
    SubscriptionStatus,
    TargetTier,
)

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
    tier: Mapped[TargetTier] = mapped_column(Enum(TargetTier), nullable=False)
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
    credit_amount: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    monthly_fee: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    sort_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    hidden: Mapped[Boolean] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )

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
    stripe_product_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    payment_method: Mapped[PaymentMethod] = mapped_column(
        Enum(PaymentMethod),
        nullable=False,
        server_default=PaymentMethod.autopay.value,
    )
    trial_start_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    start_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    end_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(
        String, nullable=True, index=True
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, name="subscriptionstatus"),
        nullable=False,
    )

    recurring_credit_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    recurring_credit_amount: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    recurring_credit_frequency: Mapped[Optional[RecurringCreditFrequency]] = (
        mapped_column(
            Enum(RecurringCreditFrequency, name="recurringcreditfrequency"),
            nullable=True,
        )
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )

    account: Mapped["Account"] = relationship("Account", back_populates="subscriptions")
    subscription_plan: Mapped["SubscriptionPlan"] = relationship("SubscriptionPlan")

    @property
    def is_valid(self):
        return self.status in [
            SubscriptionStatus.pending,
            SubscriptionStatus.active,
            SubscriptionStatus.trialing,
        ]


class ProjectSubscription(Base):
    __tablename__ = "project_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        index=True,
    )
    external_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    version: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, default=1, server_default="1"
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    subscription_plan_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    stripe_product_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(
        String, nullable=True, index=True
    )
    payment_method: Mapped[Optional[PaymentMethod]] = mapped_column(
        Enum(PaymentMethod),
        nullable=True,
    )
    base_price_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    call_price_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    order_price_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    trial_start_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    start_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    end_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[Optional[SubscriptionStatus]] = mapped_column(
        Enum(SubscriptionStatus, name="subscriptionstatus"),
        nullable=True,
    )
    deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
    )

    recurring_credit_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    recurring_credit_amount: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    recurring_credit_frequency: Mapped[Optional[RecurringCreditFrequency]] = (
        mapped_column(
            Enum(RecurringCreditFrequency, name="recurringcreditfrequency"),
            nullable=True,
        )
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )

    __table_args__ = (
        Index(
            "ix_project_id_subscription_id_unique_not_deleted",
            "project_id",
            "subscription_id",
            unique=True,
            postgresql_where=and_(deleted.is_(False)),
        ),
    )
