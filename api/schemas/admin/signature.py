from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, HttpUrl


class InitiateTermsSigningRequest(BaseModel):
    """Request to initiate terms of service signing via DocuSign"""

    signer_name: str = Field(..., description="Full name of the person signing")
    signer_email: EmailStr = Field(..., description="Email of the person signing")
    redirect_url: HttpUrl = Field(
        ..., description="URL to redirect after signing (required for DocuSign)"
    )
    frame_ancestors: list[str] | None = Field(
        None,
        description="List of allowed frame ancestor origins for embedded signing",
    )


class InitiateTermsSigningResponse(BaseModel):
    """Response from initiating terms signing"""

    success: bool = Field(..., description="Whether the request was successful")
    envelope_id: str = Field(..., description="DocuSign envelope ID")
    signing_url: str = Field(
        ..., description="URL for embedded signing with focused view"
    )
    signer_client_user_id: str = Field(
        ..., description="Unique client user ID for this signer"
    )


class CompleteTermsSigningResponse(BaseModel):
    """Response from completing terms signing"""

    success: bool = Field(..., description="Whether the request was successful")
    terms_accepted: bool = Field(..., description="Whether terms are now accepted")
    terms_signed_at: datetime = Field(
        ..., description="UTC timestamp when terms were signed"
    )
