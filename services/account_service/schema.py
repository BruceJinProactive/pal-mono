import uuid
from dataclasses import dataclass

from db.tables.accounts import AccountStatus, BusinessIndustry


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
    lead_id: uuid.UUID | None = None
    status: AccountStatus | None = None
    stripe_customer_id: str | None = None
    stripe_subscription_id: str | None = None
