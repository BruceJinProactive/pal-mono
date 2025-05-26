import uuid
from dataclasses import dataclass

from db.tables.accounts import AccountStatus, BusinessIndustry


@dataclass
class AccountParams:
    display_name: str | None
    icon_uri: str | None
    industry: BusinessIndustry | None
    business_description: str | None
    business_faq: str | None
    business_promotions: str | None
    business_catalog: str | None
    business_others: str | None
    lead_id: uuid.UUID | None = None
    status: AccountStatus | None = None
