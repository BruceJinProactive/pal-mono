import uuid
from typing import Optional

from sqlalchemy.orm import Session

from api.routes.admin import UserContext

from . import _implementation
from .schema import CampaignDetails, CampaignSummary, CreateCampaignRequest


def create_campaign(
    session: Session,
    context: UserContext,
    account_id: uuid.UUID,
    campaign_request: CreateCampaignRequest,
) -> uuid.UUID:
    """
    Create a campaign entity in the database to store the metadata.
    """
    return _implementation.create_campaign(
        session, context, account_id, campaign_request
    )


def get_campaign_detail(
    session: Session,
    context: UserContext,
    campaign_id: uuid.UUID,
) -> CampaignDetails:
    """
    Get detailed information about a campaign, including message statistics.
    """
    return _implementation.get_campaign_details(session, context, campaign_id)


def list_account_campaigns(
    session: Session,
    context: UserContext,
    account_id: uuid.UUID,
    status_filter: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[CampaignSummary], int]:
    """
    Retrieves a list of campaign summaries for the given account.
    Optionally filter by campaign status.
    """
    return _implementation.list_account_campaigns(
        session, context, account_id, status_filter, page, page_size
    )


__all__ = [
    "create_campaign",
    "get_campaign_detail",
    "list_account_campaigns",
]
