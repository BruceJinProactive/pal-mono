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
    credit_amount: Optional[int]
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
    credit_amount: Optional[int] = None
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
    credit_amount: Optional[int] = None
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
            credit_amount=self.credit_amount,
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
    end_date: Optional[datetime] = None
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
    referral_code: str | None = None

    def to_subscription_params(self) -> SubscriptionParams:
        return SubscriptionParams(
            subscription_plan_id=self.subscription_plan_id,
            payment_method=self.payment_method,
            schedule=self.schedule,
        )


class ListAccountSubscriptionsResponse(BaseModel):
    current: Optional[Subscription] = None
    scheduled: List[Subscription] = []


class UsageMetrics(BaseModel):
    """Usage metrics for the current billing period."""

    calls_used: int = 0
    calls_included: int = 0
    calls_overage: int = 0
    overage_cost: float = 0.0  # Cost of overage in dollars


class Invoice(BaseModel):
    """Invoice details."""

    id: str
    invoice_number: str | None = None
    amount_due: int  # in cents
    amount_paid: int  # in cents
    currency: str = "usd"
    status: str  # paid, open, void, uncollectible
    created: datetime
    due_date: datetime | None = None
    invoice_pdf: str | None = None  # PDF download URL
    hosted_invoice_url: str | None = None  # Stripe hosted invoice URL


class UpgradeOption(BaseModel):
    """Information about upgrade/downgrade options."""

    plan_name: str
    plan_id: str | None = None
    price_monthly: float | None = None
    price_annual: float | None = None
    featured_benefits: List[str] = (
        []
    )  # 3 randomly selected features from features_included


class GetCurrentSubscriptionResponse(BaseModel):
    subscription: Optional[Subscription] = None


class GetCurrentSubscriptionDetailsResponse(BaseModel):
    """Comprehensive subscription and billing details for the frontend."""

    # Current subscription info
    subscription: Optional[Subscription] = None
    plan_name: str | None = None
    plan_features: List[str] = []  # features_included from subscription_plan

    # Billing cycle info
    billing_cycle: str | None = None  # "monthly" or "annual"
    next_billing_date: datetime | None = None
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None

    # Usage metrics
    usage: UsageMetrics = UsageMetrics()

    # Payment info
    payment_status: str | None = None  # "active", "past_due", "canceled", etc.
    payment_method_last4: str | None = None  # Last 4 digits of card
    payment_method_brand: str | None = None  # visa, mastercard, etc.

    # Invoices
    recent_invoices: List[Invoice] = []

    # Upgrade options
    upgrade_options: List[UpgradeOption] = []
    current_plan_tier: int = (
        0  # Numeric tier value: 0=none, 1=t1, 2=t2, 3=t3, 4=enterprise
    )


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
            trial_start_date = info.data["trial_start_date"]
            if trial_start_date is not None and v < trial_start_date:
                raise ValueError("Start date must be after trial start date")

        return v

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
    referral_code: str | None = None


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


class IndependentProjectSubscription(BaseModel):
    """Schema for independent ProjectSubscription response"""

    id: uuid.UUID
    external_id: Optional[uuid.UUID] = None
    version: Optional[int] = None
    project_id: uuid.UUID
    subscription_plan: SubscriptionPlan | None = None
    payment_method: PaymentMethod | None = None
    trial_start_date: Optional[datetime] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    stripe_subscription_id: Optional[str] = None
    status: Optional[SubscriptionStatus] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class CreateIndependentProjectSubscriptionRequest(BaseModel):
    """Request for creating an independent project subscription"""

    subscription_plan_id: uuid.UUID
    payment_method: PaymentMethod
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    trial_start_date: Optional[datetime] = None
    recurring_credit_enabled: bool = False
    recurring_credit_amount: Optional[float] = None
    recurring_credit_frequency: Optional[str] = None

    def to_subscription_params(self) -> SubscriptionParams:
        from db.tables.types import RecurringCreditFrequency

        recurring_freq = None
        if self.recurring_credit_frequency:
            recurring_freq = RecurringCreditFrequency(self.recurring_credit_frequency)

        return SubscriptionParams(
            subscription_plan_id=self.subscription_plan_id,
            payment_method=self.payment_method,
            start_date=self.start_date,
            end_date=self.end_date,
            trial_start_date=self.trial_start_date,
            recurring_credit_enabled=self.recurring_credit_enabled,
            recurring_credit_amount=self.recurring_credit_amount,
            recurring_credit_frequency=recurring_freq,
            schedule=None,
        )


class CreateIndependentProjectSubscriptionResponse(BaseModel):
    """Response for creating an independent project subscription"""

    message: str
    project_subscription: IndependentProjectSubscription


class UpdateProjectSubscriptionRequest(BaseModel):
    """Request for updating a project subscription"""

    payment_method: Optional[PaymentMethod] = None
    trial_start_date: Optional[datetime] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    status: Optional[SubscriptionStatus] = None
    subscription_plan_id: Optional[uuid.UUID] = None
    recurring_credit_enabled: Optional[bool] = None
    recurring_credit_amount: Optional[float] = None
    recurring_credit_frequency: Optional[str] = None


class UpdateProjectSubscriptionResponse(BaseModel):
    """Response for updating a project subscription"""

    message: str
    project_subscription: IndependentProjectSubscription


class UpdateProjectSubscriptionStatusRequest(BaseModel):
    """Request for updating project subscription status"""

    status: SubscriptionStatus


class UpdateProjectSubscriptionStatusResponse(BaseModel):
    """Response for updating project subscription status"""

    message: str
    external_id: Optional[uuid.UUID] = None
    status: str


class CancelProjectSubscriptionResponse(BaseModel):
    """Response for cancelling a project subscription"""

    message: str
    external_id: Optional[uuid.UUID] = None


class GetProjectSubscriptionResponse(BaseModel):
    """Response for getting a project subscription"""

    project_subscription: IndependentProjectSubscription | None


class GrantAccountCreditRequest(BaseModel):
    amount: int  # amount in cent
    currency: str = "usd"  # default USD
    description: str | None = None  # A description for the credit


class GetAccountCreditResponse(BaseModel):
    balance: int  # amount in cent
    currency: str  # 3 letter lowercase currency code


class CreditGrant(BaseModel):
    id: str
    created: datetime
    credit_amount_cents: int
    credit_reduction_cents: int
    currency: str
    description: str | None
    metadata: dict[str, str]
    ending_balance: int
    issued_by: str | None
    issued_via: str | None
    request_source: str | None


class ListAccountCreditGrantsResponse(BaseModel):
    credit_grants: list[CreditGrant]


class SwitchPlanRequest(BaseModel):
    new_plan_id: uuid.UUID
    prorate: bool = True


class SwitchPlanResponse(BaseModel):
    success: bool
    subscription_id: uuid.UUID
    old_plan_name: str
    new_plan_name: str
    effective_date: datetime
    prorated: bool


class StripeCustomer(BaseModel):
    id: str
    name: str | None
    email: str | None
    balance: int
    currency: str | None


class UpdateStripeCustomerRequest(BaseModel):
    name: str | None = None
    email: str | None = None


class CreateStripeCustomerRequest(BaseModel):
    name: str | None = None
    email: str | None = None


# Coupon Management Schemas
class CreateCouponRequest(BaseModel):
    """Request to create a new Stripe coupon"""

    coupon_id: str | None = None  # Optional custom ID
    percent_off: float | None = None  # Percentage discount (0-100)
    amount_off: int | None = None  # Fixed amount in cents
    currency: str | None = None  # Required if amount_off is set
    duration: str = "once"  # 'once', 'repeating', or 'forever'
    duration_in_months: int | None = None  # Required if duration is 'repeating'
    max_redemptions: int | None = None  # Maximum times coupon can be redeemed
    redeem_by: int | None = None  # Unix timestamp for expiration
    name: str | None = None  # Human-readable name

    @field_validator("percent_off")
    def validate_percent_off(cls, v):
        if v is not None and (v <= 0 or v > 100):
            raise ValueError("percent_off must be between 0 and 100")
        return v

    @field_validator("amount_off")
    def validate_amount_off(cls, v):
        if v is not None and v <= 0:
            raise ValueError("amount_off must be positive")
        return v

    @field_validator("duration")
    def validate_duration(cls, v):
        valid_durations = ["once", "repeating", "forever"]
        if v not in valid_durations:
            raise ValueError(f"duration must be one of: {valid_durations}")
        return v


class AssignCouponRequest(BaseModel):
    """Request to assign a Stripe coupon to an account"""

    coupon_id: str


class UpdateCouponRequest(BaseModel):
    """Request to update the Stripe coupon for an account"""

    coupon_id: str


class CouponResponse(BaseModel):
    """Response containing coupon information"""

    coupon_id: str | None
    coupon_valid: bool | None = None
    coupon_details: dict | None = None


class CouponDetailsResponse(BaseModel):
    """Detailed coupon information from Stripe"""

    id: str
    name: str | None
    percent_off: float | None
    amount_off: int | None
    currency: str | None
    duration: str
    duration_in_months: int | None
    max_redemptions: int | None
    times_redeemed: int
    valid: bool
    redeem_by: int | None
