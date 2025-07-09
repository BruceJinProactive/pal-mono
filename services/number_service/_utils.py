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
