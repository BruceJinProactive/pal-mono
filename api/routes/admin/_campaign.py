import uuid
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from api.routes.admin import UserContext
from api.routes.admin._auth import authorize_user_account
from api.routes.admin._utils import not_found_error
from api.schemas.admin.campaign import (
    CampaignDetail,
    CampaignSummary,
    CreateCampaignRequest,
    CreateCampaignResponse,
    ListCampaignsResponse,
)
from db.repositories.account_repository import AccountRepository
from db.repositories.campaign_repository import (
    CampaignMessageRepository,
    CampaignRepository,
)
from db.tables.campaigns import (
    Campaign,
    CampaignChannel,
    CampaignMessage,
    CampaignMessageStatus,
)
from services import account_service


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
    # Authorize user has access to this account
    authorize_user_account(context, account_name)

    # Get account
    account = account_service.get_account(session, account_name)
    if not account:
        raise not_found_error(f"Account {account_name} not found")

    # Create campaign
    campaign = Campaign(
        account_id=account.id,
        name=campaign_request.name,
        message=campaign_request.message,
        internal_recipient=campaign_request.internal_recipient,
        channel=CampaignChannel.email,  # Default to email for now
    )

    # Save to database
    campaign_repo = CampaignRepository(session)
    campaign = campaign_repo.create_campaign(campaign)

    # Create campaign messages for recipients if specified
    if campaign_request.additional_recipients:
        message_repo = CampaignMessageRepository(session)
        for recipient in campaign_request.additional_recipients:
            message = CampaignMessage(
                campaign_id=campaign.id,
                recipient=recipient,
                status=CampaignMessageStatus.pending,
            )
            message_repo.create_campaign_message(message)

    return CreateCampaignResponse(campaign_id=campaign.id)


async def get_campaign_detail(
    campaign_id: uuid.UUID,
    context: UserContext,
    session: Session,
) -> CampaignDetail:
    """
    Get detailed information about a campaign, including message statistics.
    """
    # Get campaign
    campaign_repo = CampaignRepository(session)
    campaign = campaign_repo.get_campaign(campaign_id)
    if not campaign:
        raise not_found_error(f"Campaign {campaign_id} not found")

    # Get account name for authorization
    account_repo = AccountRepository(session)
    account = account_repo.get_account_by_id(campaign.account_id)
    if not account:
        raise not_found_error(f"Account {campaign.account_id} not found")

    # Authorize user has access to this account
    authorize_user_account(context, account.name)

    # Get message statistics
    message_stats = (
        session.query(
            CampaignMessage.status, func.count(CampaignMessage.id).label("count")
        )
        .filter(CampaignMessage.campaign_id == campaign_id)
        .group_by(CampaignMessage.status)
        .all()
    )

    # Initialize counters
    total_scheduled = 0
    total_success = 0
    total_failed = 0

    # Calculate totals
    for status, count in message_stats:
        if status == CampaignMessageStatus.pending:
            total_scheduled += count
        elif status == CampaignMessageStatus.success:
            total_success += count
        elif status == CampaignMessageStatus.failed:
            total_failed += count

    # Determine overall status
    if total_success + total_failed == 0:
        status = "initializing"
    elif total_scheduled > 0:
        status = "in_progress"
    else:
        status = "complete"

    # Get list of recipients
    recipients = (
        session.query(CampaignMessage.recipient)
        .filter(CampaignMessage.campaign_id == campaign_id)
        .all()
    )
    additional_recipients = [r[0] for r in recipients]

    return CampaignDetail(
        name=campaign.name,
        message=campaign.message,
        internal_recipient=campaign.internal_recipient,
        additional_recipients=additional_recipients,
        total_scheduled=total_scheduled,
        total_success=total_success,
        total_failed=total_failed,
        status=status,
        created_at=campaign.created_at,
    )


async def list_account_campaigns(
    account_name: str,
    status_filter: Optional[str],
    context: UserContext,
    session: Session,
) -> ListCampaignsResponse:
    """
    Retrieves a list of campaign summaries for the given account.
    Optionally filter by campaign status.
    """
    # Authorize user has access to this account
    authorize_user_account(context, account_name)

    # Get account
    account = account_service.get_account(session, account_name)
    if not account:
        raise not_found_error(f"Account {account_name} not found")

    # Get campaigns for the account
    campaign_repo = CampaignRepository(session)
    campaigns = campaign_repo.get_campaigns_by_account_id(account.id)

    # Transform campaigns into summaries
    campaign_summaries: List[CampaignSummary] = []
    for campaign in campaigns:
        # Get message statistics for this campaign
        message_stats = (
            session.query(
                CampaignMessage.status, func.count(CampaignMessage.id).label("count")
            )
            .filter(CampaignMessage.campaign_id == campaign.id)
            .group_by(CampaignMessage.status)
            .all()
        )

        # Calculate totals
        total_scheduled = sum(count for _, count in message_stats)
        total_success = sum(
            count
            for status, count in message_stats
            if status == CampaignMessageStatus.success
        )
        total_failed = sum(
            count
            for status, count in message_stats
            if status == CampaignMessageStatus.failed
        )

        # Determine status
        if total_success + total_failed == 0:
            campaign_status = "initializing"
        elif total_scheduled > total_success + total_failed:
            campaign_status = "in_progress"
        else:
            campaign_status = "complete"

        # Skip if status filter is provided and doesn't match
        if status_filter and status_filter != campaign_status:
            continue

        summary = CampaignSummary(
            id=campaign.id,
            name=campaign.name,
            internal_recipient=campaign.internal_recipient,
            total_scheduled=total_scheduled,
            status=campaign_status,
            created_at=campaign.created_at,
        )
        campaign_summaries.append(summary)

    return ListCampaignsResponse(campaigns=campaign_summaries)
