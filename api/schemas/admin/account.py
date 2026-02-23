import uuid
from typing import List
from uuid import UUID

from pydantic import BaseModel, Field

from db.tables.accounts import (
    AccountSegment,
    AccountStatus,
    BusinessIndustry,
    OnboardingMethod,
)
from db.tables.types import SubscriptionStatus, TargetTier
from services.account_service import AccountParams


class Account(BaseModel):
    """Account Model"""

    id: str
    name: str
    display_name: str
    status: AccountStatus
    icon_url: str
    industry: str | None
    business_description: str | None
    business_faq: str | None
    business_promotions: str | None
    business_catalog: str | None
    business_others: str | None
    stripe_customer_id: str | None
    projects: list[str] = []  # list of project uuids
    agents: list[str] = []  # list of agent uuids
    lead_id: UUID | None = None
    owner: str | None = None
    segment: str | None = None
    tier: str | None = None
    notes: str | None = None
    contract_signed: bool = False
    terms_accepted: bool | None = None
    phone_number: str | None = None
    channels: list[str] | None = None
    onboarding_method: OnboardingMethod
    created_at: int  # Unix timestamp in seconds
    updated_at: int | None  # Unix timestamp in seconds


class AccountSummary(BaseModel):
    """Account Summary Model for List Responses"""

    id: UUID
    name: str
    display_name: str
    status: AccountStatus
    icon_url: str
    industry: str | None
    owner: str | None = None
    segment: str | None = None
    tier: str | None = None
    contract_signed: bool = False
    terms_accepted: bool = False
    notes: str | None = None
    phone_number: str | None = None
    channels: list[str] | None = None
    created_at: int | None = None  # Unix timestamp in seconds
    onboarding_method: OnboardingMethod | None = None
    updated_at: int | None = None  # Unix timestamp in seconds
    subscription_status: SubscriptionStatus | None = None


class ListAccountsResponse(BaseModel):
    """List Accounts Response"""

    accounts: List[AccountSummary]
    total: int = Field(..., description="Total number of accounts matching filters")
    total_pages: int = Field(..., description="Total number of pages")
    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, le=150, description="Items per page")


class UpdateAccountRequest(BaseModel):
    """Update Account Request"""

    display_name: str | None = None
    status: AccountStatus | None = None
    icon_uri: str | None = None
    industry: BusinessIndustry | None = None
    business_description: str | None = None
    business_faq: str | None = None
    business_promotions: str | None = None
    business_catalog: str | None = None
    business_others: str | None = None
    owner: str | None = None
    segment: AccountSegment | None = None
    tier: TargetTier | None = None
    notes: str | None = None
    contract_signed: bool | None = None
    terms_accepted: bool | None = None
    phone_number: str | None = None
    channels: list[str] | None = None
    expected_version: int | None = None

    def to_account_params(self) -> AccountParams:
        return AccountParams(
            display_name=self.display_name,
            status=self.status,
            icon_uri=self.icon_uri,
            industry=self.industry,
            business_description=self.business_description,
            business_faq=self.business_faq,
            business_promotions=self.business_promotions,
            business_catalog=self.business_catalog,
            business_others=self.business_others,
            owner=self.owner,
            segment=self.segment,
            tier=self.tier,
            notes=self.notes,
            contract_signed=self.contract_signed,
            terms_accepted=self.terms_accepted,
            phone_number=self.phone_number,
            channels=self.channels,
        )


class CreateAccountRequest(UpdateAccountRequest):
    """Create Account Request"""

    name: str = Field(...)
    lead_id: uuid.UUID | None = None


class AccountStatisticsResponse(BaseModel):
    total_users: int
    total_sessions: int
    active_sessions: int
    escalated_sessions: int


class AccountStatusResponse(BaseModel):
    """Account Status Response"""

    id: UUID
    name: str
    status: AccountStatus
    display_name: str | None = None


class TermsStatusResponse(BaseModel):
    """Terms Acceptance Status Response"""

    id: UUID
    name: str
    terms_accepted: bool
    display_name: str | None = None


class AcceptTermsRequest(BaseModel):
    """Accept Terms Request"""

    tos_version: str = Field(
        ..., min_length=1, max_length=50, description="Version of the Terms of Service"
    )


class AcceptTermsResponse(BaseModel):
    """Accept Terms Response"""

    accepted: bool


class NotificationPreferences(BaseModel):
    """Notification Preferences"""

    email_enabled: bool = Field(
        default=True, description="Whether email notifications are enabled"
    )


class NotificationPreferencesResponse(BaseModel):
    """Notification Preferences Response"""

    notification_preferences: NotificationPreferences
    notification_email: str | None = Field(
        default=None, description="Override email address for notifications"
    )


class UpdateNotificationPreferencesRequest(BaseModel):
    """Update Notification Preferences Request"""

    email_enabled: bool | None = Field(
        default=None, description="Whether email notifications are enabled"
    )
    notification_email: str | None = Field(
        default=None, description="Override email address for notifications"
    )
