import os
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


def get_server_url():
    runtime_env = os.getenv("RUNTIME_ENV")
    if runtime_env is None:
        raise ValueError("RUNTIME_ENV environment variable is not set")
    if runtime_env == "lat":
        server_url = "https://lat-api.proactiveailb.com/v1/integrations/vapi/"
    elif runtime_env == "stg":
        server_url = "https://stg-api.proactiveailb.com/v1/integrations/vapi/"
    elif runtime_env == "prd":
        server_url = "https://api.proactiveailb.com/v1/integrations/vapi/"
    else:
        raise ValueError(f"Invalid runtime environment: {runtime_env}")
    return server_url


def get_twilio_friendly_name(project_name: str):
    runtime_env = os.getenv("RUNTIME_ENV")
    runtime_env = runtime_env or "dev"
    return f"{runtime_env}:{project_name}"
