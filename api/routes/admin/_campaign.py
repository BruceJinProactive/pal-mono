import uuid

from sqlalchemy.orm import Session

from api.routes.admin import UserContext
from api.schemas.admin.campaign import CreateCampaignRequest


async def create_campaign(
    account_name: str,
    campaign_request: CreateCampaignRequest,
    context: UserContext,
    session: Session,
):
    """
    Create a campaign entity in the database to store the metadata.
    Make sure user has permission for this account.
    """
    # TODO (@dan.liu): implement necessary logics
    raise NotImplementedError("not implemented yet")


async def get_campaign_detail(
    campaign_id: uuid.UUID,
    context: UserContext,
    session: Session,
):
    # TODO (@dan.liu): implement necessary logics
    raise NotImplementedError("not implemented yet")


async def list_account_campaigns(
    account_name: str,
    context: UserContext,
    session: Session,
):
    # TODO (@dan.liu): implement necessary logics
    raise NotImplementedError("not implemented yet")
