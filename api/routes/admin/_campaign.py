import math
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from api.routes.admin import UserContext
from api.routes.admin._auth import authorize_user_account
from api.routes.admin._utils import not_found_error
from api.schemas.admin.campaign import CreateCampaignResponse, ListCampaignsResponse
from db.repositories.account_repository import AccountRepository
from services import account_service, campaign_service
from services.campaign_service.schema import CampaignDetails, CreateCampaignRequest


async def create_campaign(
    account_name: str,
    campaign_request: CreateCampaignRequest,
    context: UserContext,
    session: Session,
) -> CreateCampaignResponse:
    """
    Create a campaign entity in the database to store the metadata.
    Make sure user has permission for this account.
    """
    account = account_service.get_account(session, account_name)
    if not account:
        raise ValueError(f"Account {account_name} not found")

    # Authorize user has access to this account
    authorize_user_account(context, account_name)

    try:
        campaign_id = campaign_service.create_campaign(
            session=session,
            context=context,
            account_id=account.id,
            campaign_request=campaign_request,
        )
        return CreateCampaignResponse(campaign_id=campaign_id)
    except ValueError as e:
        raise not_found_error(str(e))


async def get_campaign_detail(
    campaign_id: uuid.UUID,
    context: UserContext,
    session: Session,
) -> CampaignDetails:
    """
    Get detailed information about a campaign, including message statistics.
    """
    try:
        campaign_detail = campaign_service.get_campaign_detail(
            session=session,
            context=context,
            campaign_id=campaign_id,
        )
    except ValueError as e:
        raise not_found_error(str(e))

    # Get account name for authorization
    account_repository = AccountRepository(session)
    account = account_repository.get_account_by_id(campaign_detail.account_id)
    if not account:
        raise not_found_error(f"Account {campaign_detail.account_id} not found")

    # Authorize user has access to this account
    authorize_user_account(context, account.name)

    return campaign_detail


async def list_account_campaigns(
    account_name: str,
    status_filter: Optional[str],
    context: UserContext,
    session: Session,
    page: int = 1,
    page_size: int = 20,
) -> ListCampaignsResponse:
    """
    Retrieves a list of campaign summaries for the given account.
    Optionally filter by campaign status.
    """
    account = account_service.get_account(session, account_name)
    if not account:
        raise not_found_error(f"Account {account_name} not found")

    # Authorize user has access to this account
    authorize_user_account(context, account_name)

    campaigns, total = campaign_service.list_account_campaigns(
        session=session,
        context=context,
        account_id=account.id,
        status_filter=status_filter,
        page=page,
        page_size=page_size,
    )
    return ListCampaignsResponse(
        campaigns=campaigns,
        total_campaigns=total,
        total_pages=math.ceil(total / page_size),
    )
