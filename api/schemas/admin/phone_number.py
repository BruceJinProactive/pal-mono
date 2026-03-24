import uuid
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from services.number_service._utils import (
    NumberChannel,
    NumberType,
    UsageType,
    VerificationStatus,
)


class VoiceProvider(str, Enum):
    """Supported voice routing providers."""

    LIVEKIT = "livekit"


class ReserveProjectNumberRequest(BaseModel):
    """Request model for creating a new phone number or reserving an existing one."""

    channels: list[NumberChannel] = Field(
        ...,
        description="The channel(s) in which this new number is used, e.g. voice, sms",
    )
    country_code: str = Field(
        "US", description="Country code for the phone number (e.g., 'US')"
    )
    toll_free: bool = Field(True, description="Whether to create a toll-free number")
    phone_number: Optional[str] = Field(
        None,
        description="Optional existing phone number to reserve instead of creating new one",
    )
    voice_provider: VoiceProvider = Field(
        VoiceProvider.LIVEKIT,
        description="Voice routing provider (default: 'livekit')",
    )


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
    voice_provider: VoiceProvider | None = Field(
        None,
        description="Voice routing provider",
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


class PurchaseNumberRequest(BaseModel):
    """Request model for purchasing a single phone number.

    Note: Purchased numbers automatically use "AVAILABLE" as their merchant name,
    making them available for assignment to projects.
    """

    country_code: str = Field(
        "US", description="Country code for the phone number (e.g., 'US')"
    )
    toll_free: bool = Field(False, description="Whether to purchase a toll-free number")
    area_code: Optional[str] = Field(
        None,
        description="Optional area code for local numbers (e.g., '415'). "
        "Can be combined with contains for more specific searches.",
    )
    contains: Optional[str] = Field(
        None,
        description="Optional pattern for substring matching in phone numbers. "
        "This value is passed directly to Twilio's contains parameter. "
        "Examples: '555' to find numbers containing '555', '6666' for numbers containing '6666'. "
        "Can be combined with area_code for more specific searches.",
    )
    voice_provider: VoiceProvider = Field(
        VoiceProvider.LIVEKIT,
        description="Voice routing provider (default: 'livekit')",
    )


class PurchaseNumberResponse(BaseModel):
    """Response model for purchasing a single phone number."""

    phone_number: str = Field(
        ..., description="The purchased phone number in E.164 format"
    )
    merchant_name: str = Field(
        ..., description="Merchant name (will be 'env:AVAILABLE' for purchased numbers)"
    )
    country_code: str = Field(..., description="Country code for the number")
    toll_free: bool = Field(..., description="Whether this is a toll-free number")


class ReleaseNumberRequest(BaseModel):
    """Request model for releasing a standalone phone number."""

    phone_number: str = Field(
        ..., description="The phone number to release (e.g., '+15551234567')"
    )


class ReleaseNumberResponse(BaseModel):
    """Response model for releasing a phone number."""

    phone_number: str = Field(..., description="The phone number that was released")
    message: str = Field(..., description="Success message")
    released_from_twilio: bool = Field(
        ..., description="Whether the number was released from Twilio"
    )


class PhoneNumberReleaseType(str, Enum):
    """Type of phone number release operation."""

    RETURN_TO_POOL = "return_to_pool"
    DELETE_PERMANENTLY = "delete_permanently"


class EnhancedReleaseProjectNumberRequest(BaseModel):
    """Enhanced request model for releasing a phone number with options."""

    phone_number: str = Field(
        ..., description="The phone number to release (e.g., '+15551234567')"
    )
    release_type: PhoneNumberReleaseType = Field(
        PhoneNumberReleaseType.RETURN_TO_POOL,
        description="How to handle the phone number: 'return_to_pool' makes it available for reuse, 'delete_permanently' removes it completely",
    )


class EnhancedReleaseProjectNumberResponse(BaseModel):
    """Response model for enhanced phone number release."""

    phone_number: str = Field(..., description="The phone number that was released")
    release_type: PhoneNumberReleaseType = Field(
        ..., description="The type of release performed"
    )
    message: str = Field(..., description="Success message describing the action taken")
