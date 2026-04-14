from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ProjectSubscriptionData:
    """Immutable snapshot of a project subscription record.

    Enum fields are serialised to plain strings so that consumers do not
    depend on ``db.tables.types``.
    """

    id: uuid.UUID
    project_id: uuid.UUID
    subscription_id: uuid.UUID
    deleted: bool
    created_at: datetime
    external_id: uuid.UUID | None = None
    version: int | None = None
    subscription_plan_id: uuid.UUID | None = None
    stripe_product_id: str | None = None
    stripe_subscription_id: str | None = None
    payment_method: str | None = None  # PaymentMethod.value
    base_price_id: str | None = None
    call_price_id: str | None = None
    order_price_id: str | None = None
    trial_start_date: datetime | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    status: str | None = None  # SubscriptionStatus.value
    recurring_credit_enabled: bool = False
    recurring_credit_amount: float | None = None
    recurring_credit_frequency: str | None = None  # RecurringCreditFrequency.value
    updated_at: datetime | None = None
