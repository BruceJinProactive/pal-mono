import enum
from typing import TypedDict

from pydantic import BaseModel, Field


class NumberResponse(BaseModel):
    """Response model for phone number details."""

    sid: str | None = Field(None, description="The unique id of the phone number")
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


class NumberChannel(str, enum.Enum):
    """Channel types for phone number usage."""

    VOICE = "voice"
    SMS = "sms"


class VerificationStatus(str, enum.Enum):
    """Twilio toll-free verification status values."""

    IN_REVIEW = "IN_REVIEW"
    TWILIO_APPROVED = "TWILIO_APPROVED"
    UNVERIFIED = "unverified"


class UsageType(str, enum.Enum):
    """How a phone number is being used."""

    VOICE = "voice"
    SMS = "sms"
    BOTH = "both"
    UNUSED = "unused"


class NumberType(str, enum.Enum):
    """Type of phone number."""

    TOLL_FREE = "toll-free"
    OTHER = "other"
