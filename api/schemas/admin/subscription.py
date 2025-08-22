import uuid
from datetime import UTC, datetime
from typing import List, Optional

from pydantic import AnyHttpUrl, BaseModel, EmailStr, field_validator
from pydantic_core.core_schema import ValidationInfo

from api.schemas.admin.project import ProjectSummary
from db.tables.types import PaymentMethod, SubscriptionStatus, TargetTier
from services.subscription_service.schema import (
    SubscriptionParams,
    SubscriptionPlanParams,
    SubscriptionSchedule,
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
    active: bool
    sort_id: Optional[int]
    hidden: bool
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
    active: bool = True
    sort_id: Optional[int] = None
    hidden: bool = True

    @field_validator("name")
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("Plan name cannot be empty")
        return v.strip()

    @field_validator(
        "call_overage_charge", "order_overage_charge", "monthly_fee", "free_trial_days"
    )
    def validate_positive_amounts(cls, v, info: ValidationInfo):
        if v is not None and v < 0:
            raise ValueError(f"{info.field_name} must be non-negative")
        return v


class UpdateSubscriptionPlanRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    tier: Optional[TargetTier] = None
    features_included: Optional[list[str]] = None
    features_excluded: Optional[list[str]] = None
    call_quota: Optional[int] = None
    order_quota: Optional[int] = None
    call_overage_charge: Optional[int] = None
    order_overage_charge: Optional[int] = None
    free_trial_days: Optional[int] = None
    monthly_fee: Optional[int] = None
    active: Optional[bool] = None
    sort_id: Optional[int] = None
    hidden: Optional[bool] = None

    def to_subscription_plan_params(self) -> SubscriptionPlanParams:
        return SubscriptionPlanParams(
            name=self.name,
            description=self.description,
            tier=self.tier,
            features_included=self.features_included,
            features_excluded=self.features_excluded,
            call_quota=self.call_quota,
            order_quota=self.order_quota,
            call_overage_charge=self.call_overage_charge,
            order_overage_charge=self.order_overage_charge,
            free_trial_days=self.free_trial_days,
            monthly_fee=self.monthly_fee,
            active=self.active,
            sort_id=self.sort_id,
            hidden=self.hidden,
        )

    @field_validator("name")
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("Plan name cannot be empty")
        return v.strip()

    @field_validator(
        "call_overage_charge", "order_overage_charge", "monthly_fee", "free_trial_days"
    )
    def validate_positive_amounts(cls, v, info: ValidationInfo):
        if v is not None and v < 0:
            raise ValueError(f"{info.field_name} must be non-negative")
        return v


class Subscription(BaseModel):
    id: uuid.UUID
    external_id: uuid.UUID
    version: Optional[int] = None
    account_id: uuid.UUID
    subscription_plan: SubscriptionPlan | None = None
    payment_method: PaymentMethod
    trial_start_date: Optional[datetime] = None
    start_date: datetime
    end_date: datetime
    in_trial: bool
    stripe_subscription_id: Optional[str] = None
    status: SubscriptionStatus
    created_at: datetime
    updated_at: Optional[datetime] = None


class CreateSubscriptionRequest(BaseModel):
    subscription_plan_id: uuid.UUID
    payment_method: PaymentMethod
    schedule: SubscriptionSchedule | None
    project_ids: Optional[list[uuid.UUID]] = None

    def to_subscription_params(self) -> SubscriptionParams:
        return SubscriptionParams(
            subscription_plan_id=self.subscription_plan_id,
            payment_method=self.payment_method,
            schedule=self.schedule,
        )


class ListAccountSubscriptionsResponse(BaseModel):
    current: Optional[Subscription] = None
    scheduled: List[Subscription] = []


class ListSubscriptionsRequest(BaseModel):
    """Request for listing subscriptions with pagination and filtering."""

    page: int = 1
    page_size: int = 20
    account_id: Optional[uuid.UUID] = None
    status_filter: Optional[List[SubscriptionStatus]] = None

    @field_validator("page")
    def validate_page(cls, v):
        if v < 1:
            raise ValueError("Page must be greater than 0")
        return v

    @field_validator("page_size")
    def validate_page_size(cls, v):
        if v < 1 or v > 100:
            raise ValueError("Page size must be between 1 and 100")
        return v


class ListSubscriptionsResponse(BaseModel):
    """Response for listing subscriptions with pagination."""

    subscriptions: List[Subscription]
    total_subscriptions: int
    total_pages: int


class UpdateAccountSubscriptionRequest(BaseModel):
    """Request to update an account subscription."""

    payment_method: Optional[PaymentMethod] = None
    trial_start_date: Optional[datetime] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    @field_validator("start_date")
    def validate_start_date(cls, v, info):
        if v is None:
            return v

        if "trial_start_date" in info.data:
            if v < info.data["trial_start_date"]:
                raise ValueError("Start date must be after trial start date")

    @field_validator("end_date")
    def validate_end_date(cls, v, info):
        if v is None:
            return v

        if (
            "start_date" in info.data
            and info.data["start_date"] is not None
            and v <= info.data["start_date"]
        ):
            raise ValueError("End date must be after start date")

        now = datetime.now(UTC)

        if v.tzinfo is None:
            v = v.replace(tzinfo=UTC)

        if v <= now:
            raise ValueError("End date cannot be in the past")

        return v


class UpdateAccountSubscriptionResponse(BaseModel):
    """Response for updating an account subscription."""

    external_id: uuid.UUID
    version: int
    status: SubscriptionStatus


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


class CreateCheckoutSessionRequest(BaseModel):
    customer_email: EmailStr | None = None
    redirect_url_prefix: AnyHttpUrl


class ProjectSubscription(BaseModel):
    """Schema for ProjectSubscription response"""

    id: uuid.UUID
    project: ProjectSummary
    subscription_id: uuid.UUID
    deleted: bool
    created_at: datetime
    updated_at: Optional[datetime] = None


class ListProjectSubscriptionsResponse(BaseModel):
    """Response for listing project subscriptions"""

    project_subscriptions: list[ProjectSubscription]
    total_count: int


class CreateProjectSubscriptionRequest(BaseModel):
    """Request for creating a project subscription"""

    project_id: uuid.UUID


class CreateProjectSubscriptionResponse(BaseModel):
    """Response for creating a project subscription"""

    message: str
    project_subscription: ProjectSubscription


class RemoveProjectSubscriptionResponse(BaseModel):
    """Response for removing a project subscription"""

    message: str
    success: bool


class GrantAccountCreditRequest(BaseModel):
    amount: int  # amount in cent
    currency: str = "usd"  # default USD
    description: str | None = None  # A description for the credit


class GetAccountCreditResponse(BaseModel):
    balance: int  # amount in cent
    currency: str  # 3 letter lowercase currency code
