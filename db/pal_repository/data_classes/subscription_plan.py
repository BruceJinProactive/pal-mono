from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class SubscriptionPlanData:
    """Immutable snapshot of a subscription plan record.

    Enum fields are serialised to plain strings so that consumers do not
    depend on ``db.tables.types``.
    """

    id: uuid.UUID
    name: str
    tier: str  # TargetTier.value
    active: bool
    created_at: datetime
    description: str | None = None
    features_included: list[str] = field(default_factory=list)
    features_excluded: list[str] = field(default_factory=list)
    call_quota: int | None = None
    order_quota: int | None = None
    call_overage_charge: int | None = None
    order_overage_charge: int | None = None
    free_trial_days: int | None = None
    credit_amount: int | None = None
    monthly_fee: int | None = None
    sort_id: int | None = None
    hidden: bool = True
    updated_at: datetime | None = None
