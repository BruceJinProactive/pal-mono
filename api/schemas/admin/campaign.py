import uuid

from pydantic import BaseModel

from services.campaign_service import CampaignSummary


class CreateCampaignResponse(BaseModel):
    campaign_id: uuid.UUID


class ListCampaignsResponse(BaseModel):
    campaigns: list[CampaignSummary]
    total_campaigns: int
    total_pages: int
