import math
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from api.routes.admin import _builder
from api.routes.admin._auth import authorize_admin
from api.routes.admin._utils import not_found_error
from api.schemas.admin.lead import (
    CreateLeadRequest,
    Lead,
    ListLeadsResponse,
    UpdateLeadRequest,
)
from db.tables.lead import BusinessSegment, LeadStatus, TargetTier
from services import admin_service
from services.admin_service import LeadFilters, LeadParams
from services.auth_types import UserContext


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
        pos=lead_request.pos,
        channels=lead_request.channels,
        contract_signed=lead_request.contract_signed,
    )

    lead = admin_service.create_lead(
        session=session,
        context=context,
        params=params,
    )

    return _builder.build_lead(lead)


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

    leads_list = [_builder.build_lead(lead) for lead in leads]

    return ListLeadsResponse(
        leads=leads_list,
        total_leads=total_count,
        total_pages=total_pages,
    )


async def update_lead(
    lead_id: uuid.UUID,
    lead_request: UpdateLeadRequest,
    context: UserContext,
    session: Session,
) -> Lead:
    """
    Update an existing lead.

    Args:
        lead_id: ID of the lead to update
        lead_request: The lead update request data
        context: User context for authorization
        session: Database session

    Returns:
        Lead: The updated lead

    Raises:
        ValueError: If the lead is not found
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
        status=lead_request.status,
        notes=lead_request.notes,
        pos=lead_request.pos,
        channels=lead_request.channels,
        contract_signed=lead_request.contract_signed,
    )

    lead = admin_service.update_lead(
        session=session,
        context=context,
        lead_id=lead_id,
        params=params,
    )

    if not lead:
        raise not_found_error(f"Lead with ID {lead_id} not found")

    return _builder.build_lead(lead)


async def delete_lead(
    lead_id: uuid.UUID,
    context: UserContext,
    session: Session,
) -> None:
    """
    Delete a lead by ID.

    Args:
        lead_id: ID of the lead to delete
        context: User context for authorization
        session: Database session
    """
    authorize_admin(context)

    admin_service.delete_lead(
        session=session,
        context=context,
        lead_id=lead_id,
    )


async def get_lead(
    lead_id: uuid.UUID,
    context: UserContext,
    session: Session,
) -> Lead:
    """
    Get a lead by ID.

    Args:
        lead_id: ID of the lead to retrieve
        context: User context for authorization
        session: Database session

    Returns:
        Lead: The lead details

    Raises:
        ValueError: If the lead is not found
    """
    authorize_admin(context)

    lead = admin_service.get_lead(
        session=session,
        context=context,
        lead_id=lead_id,
    )

    if not lead:
        raise ValueError(f"Lead with ID {lead_id} not found")

    return _builder.build_lead(lead)
