from typing import List

from pydantic import BaseModel


class Account(BaseModel):
    """Account Model"""

    id: str
    name: str
    display_name: str
    icon_url: str


class ListAccountsResponse(BaseModel):
    """List Accounts Response"""

    accounts: List[Account]
