from typing import Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field


class EmailTemplateRequest(BaseModel):
    """Request model for sending an email with a template."""

    to_email: EmailStr = Field(..., description="Recipient email address")
    template_id: int = Field(..., description="Postmark template ID")
    template_model: Dict[str, str] = Field(..., description="Template variables")
    from_email: Optional[EmailStr] = Field(None, description="Sender email address")
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


class BatchEmailRequest(BaseModel):
    """Request model for sending multiple emails with templates."""

    emails: List[EmailTemplateRequest] = Field(
        ..., description="List of emails to send"
    )


class PostmarkResponse(BaseModel):
    """Response model for Postmark API calls."""

    error_code: Optional[int] = Field(None, description="Error code if request failed")
    message: str = Field(..., description="Response message")
    message_id: Optional[str] = Field(
        None, description="Message ID for successful sends"
    )
    submitted_at: Optional[str] = Field(
        None, description="Timestamp when email was submitted"
    )
    to: Optional[str] = Field(None, description="Recipient email address")


class BatchPostmarkResponse(BaseModel):
    """Response model for batch email API calls."""

    batch_id: Optional[str] = Field(None, description="Batch ID for the request")
    messages: List[PostmarkResponse] = Field(..., description="Results for each email")


class TemplateInfo(BaseModel):
    """Model for Postmark template information."""

    template_id: int = Field(..., description="Template ID")
    name: str = Field(..., description="Template name")
    subject: str = Field(..., description="Template subject")
    html_body: Optional[str] = Field(None, description="HTML body content")
    text_body: Optional[str] = Field(None, description="Text body content")
    associated_server_id: int = Field(..., description="Associated server ID")
    active: bool = Field(..., description="Whether template is active")
    template_type: str = Field(..., description="Template type (Standard or Layout)")


class TemplateListResponse(BaseModel):
    """Response model for listing templates."""

    templates: List[TemplateInfo] = Field(..., description="List of templates")
    total_count: int = Field(..., description="Total number of templates")
