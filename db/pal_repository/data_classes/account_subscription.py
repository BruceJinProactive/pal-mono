from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from db.pal_repository.data_classes.subscription_plan import SubscriptionPlanData


@dataclass(frozen=True)
class AccountSubscriptionData:
    """Immutable snapshot of an account subscription record.

    Enum fields are serialised to plain strings so that consumers do not
    depend on ``db.tables.types``.
    """

    id: uuid.UUID
    external_id: uuid.UUID
    account_id: uuid.UUID
    subscription_plan_id: uuid.UUID
    status: str  # SubscriptionStatus.value
    payment_method: str  # PaymentMethod.value
    start_date: datetime
    created_at: datetime
    version: int | None = None
    stripe_product_id: str | None = None
    trial_start_date: datetime | None = None
    end_date: datetime | None = None
    stripe_subscription_id: str | None = None
    recurring_credit_enabled: bool = False
    recurring_credit_amount: float | None = None
    recurring_credit_frequency: str | None = None  # RecurringCreditFrequency.value
    updated_at: datetime | None = None
    subscription_plan: SubscriptionPlanData | None = None
