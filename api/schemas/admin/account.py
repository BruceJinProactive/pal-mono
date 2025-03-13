from typing import List

from pydantic import BaseModel


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
