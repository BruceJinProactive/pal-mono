import datetime
import uuid

from pydantic import BaseModel


class CreateCampaignRequest(BaseModel):
    name: str
    message: str
    internal_recipient: bool
    additional_recipients: list[str] | None


class CreateCampaignResponse(BaseModel):
    campaign_id: uuid.UUID


class CampaignDetail(BaseModel):
    name: str
    message: str
    internal_recipient: bool
    additional_recipients: list[str] | None
    total_scheduled: int
    total_success: int
    total_failed: int
    status: str
    created_at: datetime.datetime


class CampaignSummary(BaseModel):
    name: str
    internal_recipient: bool
    total_scheduled: int
    status: str
    created_at: datetime.datetime


class ListCampaignsResponse(BaseModel):
    campaigns: list[CampaignSummary]
