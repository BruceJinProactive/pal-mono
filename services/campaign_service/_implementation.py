import os
import uuid
from typing import List, Optional

from sqlalchemy.orm import Session

from api.routes.admin import UserContext
from api.schemas.chat.message import (
    AuthorType,
    Broker,
    Channel,
    Extras,
    Message,
    Metadata,
    TextObject,
)
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
from services import relay_service
from services.campaign_service.schema import (
    DEFAULT_CAMPAIGN_STAT,
    CampaignDetails,
    CampaignStat,
    CampaignSummary,
    CreateCampaignRequest,
)

# Hoist default once
DEFAULT_TWILIO_NUMBER = os.getenv("DEFAULT_TWILIO_NUMBER", "+18553762332")


def create_campaign(
    session: Session,
    context: UserContext,
    account_id: uuid.UUID,
    campaign_request: CreateCampaignRequest,
) -> uuid.UUID:
    """
    Create a campaign entity in the database to store the metadata.
    """
    campaign_repo = CampaignRepository(session)
    message_repo = CampaignMessageRepository(session)

    # Create campaign
    campaign = Campaign(
        account_id=account_id,
        name=campaign_request.name,
        message=campaign_request.message,
        internal_recipient=campaign_request.internal_recipient,
        channel=CampaignChannel.sms,
    )
    # Save to database
    campaign = campaign_repo.create_campaign(campaign)

    # Create campaign messages for recipients if specified
    if campaign_request.additional_recipients:
        for recipient in campaign_request.additional_recipients:
            message = CampaignMessage(
                campaign_id=campaign.id,
                recipient=recipient,
                status=CampaignMessageStatus.pending,
            )
            message_repo.create_campaign_message(message)
            # Send the campaign message using the relay service
            error_msg = _send_msg_to_twilio(
                message=campaign.message,
                to=recipient,
            )

            if error_msg:
                message.status = CampaignMessageStatus.failed
                message.error_detail = error_msg
            else:
                message.status = CampaignMessageStatus.success

            message_repo.update_campaign_message(message)

    return campaign.id


def _send_msg_to_twilio(message: str, to: str) -> str | None:
    """
    Send an SMS message using the relay service.

    Args:
        message: The message content to send
        to: The recipient phone number

    Returns:
        str | None: Error message if failed or None if succeeded
    """
    # Create a Message object for the SMS
    sms_message = Message(
        author_type=AuthorType.SYSTEM,
        sender_identifier=DEFAULT_TWILIO_NUMBER,
        recipient_identifier=to,
        channel=Channel.SMS,
        broker=Broker.TWILIO,
        text=TextObject(body=message),
        metadata=Metadata(testing=False),
        extras=Extras(),
    )

    # Send the message through the relay service
    response = relay_service.send_message(sms_message)
    if response.get("status") == "scheduled":
        return None
    else:
        return str(response.get("error_message", "Unknown error"))


def get_campaign_details(
    session: Session,
    context: UserContext,
    campaign_id: uuid.UUID,
) -> CampaignDetails:
    """
    Get detailed information about a campaign, including message statistics.
    """
    # Get campaign
    campaign_repo = CampaignRepository(session)

    campaign = campaign_repo.get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stat = _get_campaign_stat(session, campaign_id)

    # Get list of recipients
    campaign_recipients = campaign_repo.get_campaign_recipients(campaign_id)

    return CampaignDetails(
        name=campaign.name,
        account_id=campaign.account_id,
        message=campaign.message,
        internal_recipient=campaign.internal_recipient,
        additional_recipients=campaign_recipients,
        total_scheduled=stat.total_scheduled,
        total_success=stat.total_success,
        total_failed=stat.total_failed,
        status=stat.status,
        created_at=campaign.created_at,
    )


def list_account_campaigns(
    session: Session,
    context: UserContext,
    account_id: uuid.UUID,
    status_filter: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[CampaignSummary], int]:
    campaign_repo = CampaignRepository(session)
    skip = (page - 1) * page_size
    campaigns, total = campaign_repo.get_campaigns_by_account_id(
        account_id, skip=skip, limit=page_size
    )

    # Transform campaigns into summaries
    campaign_summaries: List[CampaignSummary] = []
    for campaign in campaigns:
        stat = _get_campaign_stat(session, campaign.id)

        # Apply status filter if specified
        if status_filter and stat.status != status_filter:
            continue

        campaign_summaries.append(
            CampaignSummary(
                id=campaign.id,
                name=campaign.name,
                internal_recipient=campaign.internal_recipient,
                total_scheduled=stat.total_scheduled,
                status=stat.status,
                created_at=campaign.created_at,
            )
        )

    return campaign_summaries, total


def _get_campaign_stat(session: Session, campaign_id: uuid.UUID) -> CampaignStat:
    # Get message statistics
    message_repo = CampaignMessageRepository(session)
    message_stats = message_repo.get_message_status_counts_for_campaign(campaign_id)

    if not message_stats:
        return DEFAULT_CAMPAIGN_STAT

    # Initialize counters
    total_scheduled = len(message_stats)
    total_success = 0
    total_failed = 0

    # Calculate totals
    for status, count in message_stats:
        if status == CampaignMessageStatus.success:
            total_success += count
        elif status == CampaignMessageStatus.failed:
            total_failed += count

    # Determine overall status
    total_completed = total_success + total_failed
    if total_completed == 0:
        status = "initializing"
    elif total_completed == total_scheduled:
        status = "complete"
    else:
        status = "in_progress"

    return CampaignStat(
        total_scheduled=total_scheduled,
        total_success=total_success,
        total_failed=total_failed,
        status=status,
    )
