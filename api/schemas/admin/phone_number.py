import enum

from pydantic import BaseModel, Field


class NumberChannel(str, enum.Enum):
    VOICE = "voice"
    SMS = "sms"


class ReserveProjectNumberRequest(BaseModel):
    """Request model for creating a new phone number."""

    channels: list[NumberChannel] = Field(
        ...,
        description="The channel(s) in which this new number is used, e.g. voice, sms",
    )
    country_code: str = Field(
        "US", description="Country code for the phone number (e.g., 'US')"
    )
    toll_free: bool = Field(True, description="Whether to create a toll-free number")


class ReleaseProjectNumberRequest(BaseModel):
    """Request model for releasing a phone number"""

    phone_number: str = Field(..., description="The phone number to be released")
