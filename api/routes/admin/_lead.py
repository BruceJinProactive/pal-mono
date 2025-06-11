import math
from typing import Optional

from sqlalchemy.orm import Session

from api.routes.admin._auth import authorize_admin
from api.routes.admin._utils import UserContext
from api.schemas.admin.lead import (
    CreateLeadRequest,
    Lead,
    LeadSummary,
    ListLeadsResponse,
)
from db.tables.lead import BusinessSegment, LeadStatus, TargetTier
from services import admin_service
from services.admin_service import LeadFilters, LeadParams


async def create_lead(
    lead_request: CreateLeadRequest,
    context: UserContext,
    session: Session,
) -> Lead:
    """
    Create a new lead.

    Args:
        lead_request: The lead creation request data
        context: User context for authorization
        session: Database session

    Returns:
        Lead: The created lead
    """
    authorize_admin(context)
    # Convert request to LeadParams
    params = LeadParams(
        business_name=lead_request.business_name,
        business_address=lead_request.business_address,
        logo_uri=lead_request.logo_uri,
        segment=lead_request.segment,
        tier=lead_request.tier,
        owner=lead_request.owner,
        hubspot_record_id=lead_request.hubspot_record_id,
        notes=lead_request.notes,
    )

    lead = admin_service.create_lead(
        session=session,
        context=context,
        params=params,
    )

    return Lead.from_db(lead)


async def list_leads(
    context: UserContext,
    session: Session,
    page: int = 1,
    page_size: int = 20,
    status: Optional[list[LeadStatus]] = None,
    segment: Optional[list[BusinessSegment]] = None,
    tier: Optional[list[TargetTier]] = None,
    keyword: Optional[str] = None,
) -> ListLeadsResponse:
    """
    Retrieve a paginated list of leads with optional filters.

    Args:
        context: User context for authorization
        session: Database session
        page: Page number (starts at 1)
        page_size: Number of items per page
        status: Optional list of statuses to filter by
        segment: Optional list of segments to filter by
        tier: Optional list of tiers to filter by
        keyword: Optional keyword to search in business_name and owner fields

    Returns:
        ListLeadsResponse: Paginated list of leads
    """
    authorize_admin(context)
    # Convert query parameters to LeadFilter
    filter_params = LeadFilters(
        page=page,
        page_size=page_size,
        status_filter=status,
        segment_filter=segment,
        tier_filter=tier,
        keyword=keyword,
    )

    leads, total_count = admin_service.list_leads(
        session=session,
        filter_params=filter_params,
    )

    total_pages = math.ceil(total_count / page_size)

    lead_summaries = [LeadSummary.from_db(lead) for lead in leads]

    return ListLeadsResponse(
        leads=lead_summaries,
        total_leads=total_count,
        total_pages=total_pages,
    )
