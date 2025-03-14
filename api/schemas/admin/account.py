from typing import List

from pydantic import BaseModel, Field


class Account(BaseModel):
    """Account Model"""

    id: str
    name: str
    display_name: str
    icon_url: str
    business_description: str | None
    business_faq: str | None
    business_promotions: str | None
    business_catalog: str | None
    business_others: str | None
    projects: list[str] = []  # list of project uuids
    agents: list[str] = []  # list of agent uuids


class ListAccountsResponse(BaseModel):
    """List Accounts Response"""

    accounts: List[Account]


class CreateAccountRequest(BaseModel):
    """Create Account Request"""

    name: str = Field(...)
    display_name: str | None = None
    icon_uri: str | None = None
    business_description: str | None = None
    business_faq: str | None = None
    business_promotions: str | None = None
    business_catalog: str | None = None
    business_others: str | None = None


class UpdateAccountRequest(BaseModel):
    """Update Account Request"""

    display_name: str | None = None
    icon_uri: str | None = None
    business_description: str | None = None
    business_faq: str | None = None
    business_promotions: str | None = None
    business_catalog: str | None = None
    business_others: str | None = None
