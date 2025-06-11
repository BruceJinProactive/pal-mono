from datetime import datetime
from typing import List
from uuid import UUID

from pydantic import BaseModel

from db.tables.lead import BusinessSegment, LeadStatus, TargetTier


class CreateLeadRequest(BaseModel):
    """Create Lead Request"""

    business_name: str  # Required field
    business_address: str | None = None
    logo_uri: str | None = None
    segment: BusinessSegment | None = None
    tier: TargetTier | None = None
    owner: str | None = None
    hubspot_record_id: str | None = None
    notes: str | None = None


class UpdateLeadRequest(BaseModel):
    """Update Lead Request"""

    business_name: str | None = None
    business_address: str | None = None
    logo_uri: str | None = None
    segment: BusinessSegment | None = None
    tier: TargetTier | None = None
    owner: str | None = None
    hubspot_record_id: str | None = None
    status: LeadStatus | None = None
    notes: str | None = None


class Lead(BaseModel):
    """Lead Detail Model"""

    id: UUID
    business_name: str | None
    business_address: str | None
    logo_uri: str | None
    segment: BusinessSegment | None
    tier: TargetTier | None
    owner: str | None
    hubspot_record_id: str | None
    status: LeadStatus
    notes: str | None
    created_at: datetime
    updated_at: datetime | None


class ListLeadsResponse(BaseModel):
    """List Leads Response"""

    leads: List[Lead]
    total_leads: int
    total_pages: int
