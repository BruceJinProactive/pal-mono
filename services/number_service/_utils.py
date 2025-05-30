from typing import Optional, TypedDict


class NumberDetails(TypedDict):
    """Details for a phone number."""

    number: str
    merchant_name: str
    project_name: Optional[str]
    toll_free: bool
    country_code: str


class AssistantConfig(TypedDict):
    """Configuration for creating a Vapi assistant."""

    merchant_name: str
    model_url: str
    model_name: str
    server_url: str
