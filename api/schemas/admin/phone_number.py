import uuid
from typing import Optional

from pydantic import BaseModel, Field

from services.number_service._utils import (
    NumberChannel,
    NumberType,
    UsageType,
    VerificationStatus,
)


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


class PhoneNumberInfo(BaseModel):
    """Information about a phone number from Twilio."""

    phone_number: str = Field(..., description="The phone number in E.164 format")
    friendly_name: Optional[str] = Field(
        None, description="Human-readable name for the number"
    )
    sid: str = Field(..., description="Twilio's unique identifier for this number")
    status: Optional[VerificationStatus] = Field(
        None, description="Verification status for toll-free numbers"
    )

    # Project and account association fields (supports multiple projects per number)
    project_ids: Optional[list[uuid.UUID]] = Field(
        None, description="IDs of projects using this number"
    )
    project_names: Optional[list[str]] = Field(
        None, description="Names of projects using this number"
    )
    account_ids: Optional[list[uuid.UUID]] = Field(
        None, description="IDs of accounts owning the projects"
    )
    account_names: Optional[list[str]] = Field(
        None, description="Names of accounts owning the projects"
    )
    usage_type: Optional[UsageType] = Field(
        None, description="How the number is used: 'voice', 'sms', 'both', or 'unused'"
    )
    number_type: Optional[NumberType] = Field(
        None,
        description="Type of phone number: 'toll-free' or 'other'",
    )


class ListPhoneNumbersResponse(BaseModel):
    """Response model for listing phone numbers."""

    numbers: list[PhoneNumberInfo] = Field(..., description="List of phone numbers")
    page: Optional[int] = Field(
        None, description="Current page number (1-based) if pagination was used"
    )
    page_size: Optional[int] = Field(
        None, description="Page size if pagination was used"
    )
    has_more: Optional[bool] = Field(
        None, description="Whether there are more pages available"
    )
