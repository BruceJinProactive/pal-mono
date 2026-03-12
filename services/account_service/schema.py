from dataclasses import dataclass
from uuid import UUID

from db.tables.accounts import (
    AccountSegment,
    AccountStatus,
    BusinessIndustry,
    OnboardingMethod,
)
from db.tables.types import TargetTier


@dataclass
class AccountParams:
    display_name: str | None = None
    icon_uri: str | None = None
    industry: BusinessIndustry | None = None
    business_description: str | None = None
    business_faq: str | None = None
    business_promotions: str | None = None
    business_catalog: str | None = None
    business_others: str | None = None
    status: AccountStatus | None = None
    stripe_customer_id: str | None = None
    stripe_subscription_id: str | None = None
    current_subscription_id: UUID | None = None
    owner: str | None = None
    segment: AccountSegment | None = None
    tier: TargetTier | None = None
    notes: str | None = None
    contract_signed: bool | None = None
    phone_number: str | None = None
    channels: list[str] | None = None
    onboarding_method: OnboardingMethod | None = None
    notification_preferences: dict | None = None
    notification_email: str | None = None
