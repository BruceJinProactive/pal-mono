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
from db.tables.types import TargetTier
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
    terms_accepted: bool = False
    phone_number: str | None = None
    channels: list[str] | None = None
    onboarding_method: OnboardingMethod


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
    notes: str | None = None
    phone_number: str | None = None
    channels: list[str] | None = None
    created_at: int | None = None  # Unix timestamp in seconds


class ListAccountsResponse(BaseModel):
    """List Accounts Response"""

    accounts: List[AccountSummary]


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
    phone_number: str | None = None
    channels: list[str] | None = None

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


class AcceptTermsResponse(BaseModel):
    """Accept Terms Response"""

    accepted: bool
