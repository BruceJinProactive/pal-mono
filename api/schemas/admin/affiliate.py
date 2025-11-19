import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, field_validator


class CreateAffiliateRequest(BaseModel):
    """Request model for creating an affiliate."""

    email: EmailStr
    first_name: str
    last_name: str
    campaign_id: str | None = None
    token: str | None = None
    stripe_customer_id: str | None = None
    paypal_email: EmailStr | None = None
    wise_email: EmailStr | None = None

    @field_validator("token")
    @classmethod
    def validate_token(cls, v: str | None) -> str | None:
        """
        Validate and sanitize token to meet Rewardful requirements.
        Token can only contain letters, numbers, and dashes.
        """
        if v is None:
            return v

        sanitized = re.sub(r"[^a-zA-Z0-9-]", "-", v)
        sanitized = re.sub(r"-+", "-", sanitized)
        sanitized = sanitized.strip("-")

        return sanitized if sanitized else None


class UpdateAffiliateRequest(BaseModel):
    """Request model for updating an affiliate."""

    email: EmailStr | None = None
    first_name: str | None = None
    last_name: str | None = None
    paypal_email: EmailStr | None = None
    wise_email: EmailStr | None = None
    state: Literal["active", "disabled"] | None = None


class AffiliateResponse(BaseModel):
    """Response model for affiliate data."""

    id: UUID
    rewardful_id: str
    rewardful_data: dict
