import gc
import os
import sys
from typing import TypedDict

from pydantic import BaseModel, Field


class NumberResponse(BaseModel):
    """Response model for phone number details."""

    number: str = Field(..., description="The phone number in E.164 format")
    merchant_name: str = Field(..., description="The name associated with the number")
    toll_free: bool = Field(..., description="Whether this is a toll-free number")
    country_code: str = Field(..., description="Country code for the phone number")

    class Config:
        """Pydantic model configuration."""

        from_attributes = True  # Allow ORM model conversion


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
    if runtime_env in ["lat", "dev"]:
        server_url = "https://lat-api.proactiveailab.com/v1/integrations/vapi/"
    elif runtime_env == "stg":
        server_url = "https://stg-api.proactiveailab.com/v1/integrations/vapi/"
    elif runtime_env == "prd":
        server_url = "https://api.proactiveailab.com/v1/integrations/vapi/"
    else:
        raise ValueError(f"Invalid runtime environment: {runtime_env}")
    return server_url


def get_twilio_friendly_name(project_name: str):
    runtime_env = os.getenv("RUNTIME_ENV")
    runtime_env = runtime_env or "dev"
    return f"{runtime_env}:{project_name}"


class DynamicModuleImportManager:
    """Context manager to track and cleanup dynamically imported modules."""

    def __init__(self):
        self.modules_before = set()
        self.modules_to_cleanup = set()

    def __enter__(self):
        self.modules_before = set(sys.modules.keys())
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        modules_after = set(sys.modules.keys())
        self.modules_to_cleanup = modules_after - self.modules_before

        # Remove newly imported modules
        for module in self.modules_to_cleanup:
            if module in sys.modules:
                del sys.modules[module]

        # Force garbage collection
        gc.collect()
