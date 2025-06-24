import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import AnyHttpUrl, BaseModel, EmailStr, PositiveInt, field_validator

from db.tables.types import PlanTier, SubscriptionStatus, SubscriptionType
from services.subscription_service.schema import (
    SubscriptionOverride,
    SubscriptionParams,
    SubscriptionPlanParams,
)


class SubscriptionPlan(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str]
    tier: PlanTier
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
    tier: PlanTier
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


class UpdateSubscriptionPlanRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    tier: Optional[PlanTier] = None
    features_included: Optional[list[str]] = None
    features_excluded: Optional[list[str]] = None
    call_quota: Optional[int] = None
    order_quota: Optional[int] = None
    call_overage_charge: Optional[int] = None
    order_overage_charge: Optional[int] = None
    free_trial_days: Optional[int] = None
    monthly_fee: Optional[int] = None
    stripe_price_id: Optional[str] = None
    active: Optional[bool] = None
    sort_id: Optional[int] = None

    def to_subscription_plan_params(self) -> SubscriptionPlanParams:
        return SubscriptionPlanParams(
            name=self.name or "",
            description=self.description or "",
            tier=self.tier or PlanTier.t1,
            features_included=self.features_included or [],
            features_excluded=self.features_excluded or [],
            call_quota=self.call_quota,
            order_quota=self.order_quota,
            call_overage_charge=self.call_overage_charge,
            order_overage_charge=self.order_overage_charge,
            free_trial_days=self.free_trial_days,
            monthly_fee=self.monthly_fee,
            stripe_price_id=self.stripe_price_id,
            active=self.active or True,
            sort_id=self.sort_id,
        )

    @field_validator("name")
    def validate_name(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError("Plan name cannot be empty")
        return v.strip() if v else v

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
    external_id: uuid.UUID
    version: Optional[int] = None
    account_id: uuid.UUID
    subscription_plan_id: uuid.UUID
    subscription_type: SubscriptionType
    start_date: datetime
    end_date: datetime
    call_quota: Optional[int] = None
    order_quota: Optional[int] = None
    call_overage_charge: Optional[int] = None
    order_overage_charge: Optional[int] = None
    monthly_fee: Optional[int] = None
    stripe_subscription_id: Optional[str] = None
    status: SubscriptionStatus
    created_at: datetime
    updated_at: Optional[datetime] = None


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


class ListAccountSubscriptionsResponse(BaseModel):
    current: Optional[Subscription] = None
    scheduled: List[Subscription] = []


class UpdateAccountSubscriptionStatusRequest(BaseModel):
    status: SubscriptionStatus

    @field_validator("status")
    def validate_status(cls, v):
        allowed_statuses = [SubscriptionStatus.active, SubscriptionStatus.pending]
        if v not in allowed_statuses:
            raise ValueError(
                f"Status must be one of: {[s.value for s in allowed_statuses]}"
            )
        return v


class UpdateAccountSubscriptionStatusResponse(BaseModel):
    message: str
    external_id: uuid.UUID
    status: str
