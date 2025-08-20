import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from db.tables.types import PaymentMethod, SubscriptionStatus, TargetTier


class SubscriptionPlanParams(BaseModel):
    name: str | None = None
    tier: TargetTier | None = None
    description: Optional[str] = None
    features_included: Optional[List[str]] = None
    features_excluded: Optional[List[str]] = None
    call_quota: Optional[int] = None
    order_quota: Optional[int] = None
    call_overage_charge: Optional[int] = None
    order_overage_charge: Optional[int] = None
    free_trial_days: Optional[int] = None
    monthly_fee: Optional[int] = None
    active: bool | None = None
    sort_id: int | None = None
    hidden: bool | None = True


class AccountSubscriptionParams(BaseModel):
    version: int
    account_id: uuid.UUID
    subscription_plan_id: uuid.UUID
    payment_method: PaymentMethod
    trial_start_date: Optional[datetime] = None
    start_date: datetime
    end_date: datetime
    call_quota: Optional[int] = None
    order_quota: Optional[int] = None
    call_overage_charge: Optional[int] = None
    order_overage_charge: Optional[int] = None
    monthly_fee: Optional[int] = None
    stripe_subscription_id: Optional[str] = None
    status: SubscriptionStatus


class SubscriptionSchedule(BaseModel):
    trial_start_date: datetime | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    stripe_subscription_id: str | None = None


class SubscriptionParams(BaseModel):
    subscription_plan_id: uuid.UUID
    payment_method: PaymentMethod
    schedule: SubscriptionSchedule | None = None


class StripeSubscriptionDetails(BaseModel):
    subscription_id: str
    status: str
    collection_method: str
    billing_cycle_anchor: datetime
    current_period_charge: int
    included_project_ids: list[uuid.UUID]


class StripeCheckoutResponse(BaseModel):
    account_id: uuid.UUID
    customer_id: str
    stripe_subscription_id: str
    subscription_external_id: uuid.UUID
