from datetime import datetime
from typing import List
from uuid import UUID

from pydantic import BaseModel

import db
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


class LeadSummary(BaseModel):
    """Lead Summary Model for List Responses"""

    id: UUID
    business_name: str | None
    business_address: str | None
    segment: BusinessSegment | None
    tier: TargetTier | None
    owner: str | None
    status: LeadStatus
    created_at: datetime
    updated_at: datetime | None

    @classmethod
    def from_db(cls, db_lead: db.Lead) -> "LeadSummary":
        return LeadSummary(
            id=db_lead.id,
            business_name=db_lead.business_name,
            business_address=db_lead.business_address,
            segment=db_lead.segment,
            tier=db_lead.tier,
            owner=db_lead.owner,
            status=db_lead.status,
            created_at=db_lead.created_at,
            updated_at=db_lead.updated_at,
        )


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

    @classmethod
    def from_db(cls, db_lead: db.Lead) -> "Lead":
        return Lead(
            id=db_lead.id,
            business_name=db_lead.business_name,
            business_address=db_lead.business_address,
            logo_uri=db_lead.logo_uri,
            segment=db_lead.segment,
            tier=db_lead.tier,
            owner=db_lead.owner,
            hubspot_record_id=db_lead.hubspot_record_id,
            status=db_lead.status,
            notes=db_lead.notes,
            created_at=db_lead.created_at,
            updated_at=db_lead.updated_at,
        )


class ListLeadsResponse(BaseModel):
    """List Leads Response"""

    leads: List[LeadSummary]
    total_leads: int
    total_pages: int
