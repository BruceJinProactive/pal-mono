from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from db.tables.subscriptions import SubscriptionType
from db.tables.types import TargetTier


class SubscriptionPlanParams(BaseModel):
    name: str
    tier: TargetTier
    description: Optional[str] = None
    features_included: List[str] = []
    features_excluded: List[str] = []
    call_quota: Optional[int] = None
    order_quota: Optional[int] = None
    call_overage_charge: Optional[int] = None
    order_overage_charge: Optional[int] = None
    free_trial_days: Optional[int] = None
    monthly_fee: Optional[int] = None
    stripe_price_id: Optional[str] = None
    active: bool = True
    sort_id: Optional[int] = None


class SubscriptionOverride(BaseModel):
    start_date: datetime | None = None
    end_date: datetime | None = None
    call_quota: int | None = None
    order_quota: int | None = None
    call_overage_charge: int | None = None
    order_overage_charge: int | None = None
    monthly_fee: int | None = None
    stripe_subscription_id: str | None = None


class SubscriptionParams(BaseModel):
    subscription_plan_id: str
    subscription_type: SubscriptionType
    override: SubscriptionOverride | None = None
