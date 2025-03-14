from dataclasses import dataclass


@dataclass
class AccountParams:
    display_name: str | None
    icon_uri: str | None
    business_description: str | None
    business_faq: str | None
    business_promotions: str | None
    business_catalog: str | None
    business_others: str | None
