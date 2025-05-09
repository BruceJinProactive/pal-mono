import uuid

from sqlalchemy.orm import Session

from api.routes.admin import UserContext


async def create_campaign(
    account_name: str,
    context: UserContext,
    session: Session,
):
    """
    Create a campaign entity in the database to store the metadata.
    Make sure user has permission for this account.
    """
    # TODO (@dan.liu): implement necessary logics
    pass


async def submit_campaign_message(
    account_name: str,
    campaign_id: uuid.UUID,
    context: UserContext,
    session: Session,
):
    """
    Uses the campaign id to retrieve the campaign metadata and then send a message
    to the recipient using relay service. Make sure user has permission to the associated
    account.
    """
    # TODO (@dan.liu): implement necessary logics
    pass
