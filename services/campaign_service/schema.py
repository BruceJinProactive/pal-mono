import uuid
from datetime import datetime

from pydantic import BaseModel


class CampaignStat(BaseModel):
    total_scheduled: int
    total_success: int
    total_failed: int
    status: str


DEFAULT_CAMPAIGN_STAT = CampaignStat(
    total_scheduled=0,
    total_success=0,
    total_failed=0,
    status="unknown",
)


class CampaignDetails(BaseModel):
    name: str
    account_id: uuid.UUID
    message: str
    internal_recipient: bool
    additional_recipients: list[str] | None
    total_scheduled: int
    total_success: int
    total_failed: int
    status: str
    created_at: datetime


class CampaignSummary(BaseModel):
    """Summary model for campaign list responses"""

    id: uuid.UUID
    name: str
    internal_recipient: bool
    total_scheduled: int
    status: str  # One of: initializing | in_progress | complete
    created_at: datetime


class CreateCampaignRequest(BaseModel):
    name: str
    message: str
    internal_recipient: bool
    additional_recipients: list[str] | None
