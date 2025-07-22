from dataclasses import dataclass

from db.tables.accounts import AccountSegment, AccountStatus, BusinessIndustry
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
    owner: str | None = None
    segment: AccountSegment | None = None
    tier: TargetTier | None = None
    notes: str | None = None
    contract_signed: bool | None = None
