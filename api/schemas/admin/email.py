from typing import Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field

from services.email_service._implementation import DEFAULT_FROM_EMAIL


class SendEmailRequest(BaseModel):
    """Request model for sending a single email with template."""

    to_email: EmailStr = Field(..., description="Recipient email address")
    template_id: int = Field(..., description="Postmark template ID")
    template_model: Dict[str, str] = Field(..., description="Template variables")
    from_email: Optional[EmailStr] = Field(
        default=DEFAULT_FROM_EMAIL, description="Sender email address"
    )
    cc_emails: Optional[List[EmailStr]] = Field(
        None, description="CC recipient email addresses"
    )
    bcc_emails: Optional[List[EmailStr]] = Field(
        None, description="BCC recipient email addresses"
    )
    reply_to: Optional[EmailStr] = Field(None, description="Reply-to email address")
    tag: Optional[str] = Field(None, description="Email tag for tracking")
    track_opens: bool = Field(True, description="Whether to track email opens")
    track_links: str = Field("HtmlAndText", description="Link tracking preference")


class SendBatchEmailsRequest(BaseModel):
    """Request model for sending multiple emails with templates."""

    emails: List[SendEmailRequest] = Field(..., description="List of emails to send")


class GetTemplateInfoRequest(BaseModel):
    """Request model for getting template information."""

    template_id: int = Field(..., description="Postmark template ID")


class ListTemplatesRequest(BaseModel):
    """Request model for listing templates."""

    count: int = Field(50, description="Number of templates to return (max 100)")
    offset: int = Field(0, description="Number of templates to skip")
