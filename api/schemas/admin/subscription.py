import uuid
from datetime import datetime
from typing import Optional

from pydantic import AnyHttpUrl, BaseModel, EmailStr, PositiveInt, field_validator

from db.tables.subscriptions import SubscriptionStatus
from db.tables.types import TargetTier
from services.subscription_service.schema import (
    SubscriptionOverride,
    SubscriptionParams,
    SubscriptionType,
)


class SubscriptionPlan(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str]
    tier: TargetTier
    features_included: list[str]
    features_excluded: list[str]
    call_quota: Optional[int]
    order_quota: Optional[int]
    call_overage_charge: Optional[int]
    order_overage_charge: Optional[int]
    free_trial_days: Optional[int]
    monthly_fee: Optional[int]
    stripe_price_id: Optional[str]
    active: bool
    sort_id: Optional[int]
    created_at: datetime
    updated_at: Optional[datetime]


class CreateSubscriptionPlanRequest(BaseModel):
    name: str
    description: Optional[str] = None
    tier: TargetTier
    features_included: list[str] = []
    features_excluded: list[str] = []
    call_quota: Optional[int] = None
    order_quota: Optional[int] = None
    call_overage_charge: Optional[int] = None
    order_overage_charge: Optional[int] = None
    free_trial_days: Optional[int] = None
    monthly_fee: Optional[int] = None
    stripe_price_id: Optional[str] = None
    active: bool = True
    sort_id: Optional[int] = None

    @field_validator("name")
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("Plan name cannot be empty")
        return v.strip()

    @field_validator("call_overage_charge", "order_overage_charge", "monthly_fee")
    def validate_positive_amounts(cls, v):
        if v is not None and v < 0:
            raise ValueError("Charges and fees must be non-negative")
        return v

    @field_validator("call_quota", "order_quota", "free_trial_days")
    def validate_positive_numbers(cls, v):
        if v is not None and v <= 0:
            raise ValueError("Quotas and trial days must be positive")
        return v


class Subscription(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    subscription_plan_id: uuid.UUID
    status: SubscriptionStatus
    start_date: datetime
    end_date: datetime
    call_quota: int
    order_quota: int
    call_overage_charge: int
    order_overage_charge: int
    monthly_fee: int
    created_at: datetime
    updated_at: Optional[datetime]


class CreateSubscriptionRequest(BaseModel):
    subscription_plan_id: uuid.UUID
    subscription_type: SubscriptionType
    override: SubscriptionOverride | None

    def to_subscription_params(self) -> SubscriptionParams:
        return SubscriptionParams(
            subscription_plan_id=str(self.subscription_plan_id),
            subscription_type=self.subscription_type,
            override=self.override,
        )


class CheckoutParams(BaseModel):
    account_name: str
    customer_email: EmailStr
    price_id: str
    redirect_url_prefix: AnyHttpUrl
    quantity: PositiveInt = 1

    @field_validator("price_id")
    def validate_price_id(cls, v):
        if not v.startswith("price_"):
            raise ValueError('Price ID must start with "price_"')
        return v
