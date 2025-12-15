"""
Usage tracking service for Stripe billing.

This module handles tracking usage from conversations to Stripe,
treating the conversations table as the single source of truth.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

import db
from db.repositories.conversation_repository import ConversationRepositoryAsync
from db.tables.conversations import ConversationStatus
from services.subscription_service._stripe_product import get_call_meter_event_name
from services.subscription_service.stripe_usage_billing import send_meter_event
from utils.log import logger


def _is_conversation_meaningful(conversation: db.Conversation) -> tuple[bool, str]:
    """
    Check if a conversation is meaningful for billing purposes.

    A conversation is meaningful if:
    1. Status is ending/ended (CLOSING or CLOSED)
    2. Not marked as a test conversation
    3. Has a valid call_id (indicates it was a voice call)

    Args:
        conversation: Conversation object to check

    Returns:
        Tuple of (is_meaningful, reason)
    """
    # Must be ending or ended (CLOSING status is set by VAPI webhook, CLOSED is set later)
    if conversation.status not in [
        ConversationStatus.CLOSING,
        ConversationStatus.CLOSED,
    ]:
        return False, f"Status is {conversation.status.value}, not ending/ended"

    # Must not be a test
    if conversation.is_test:
        return False, "Marked as test conversation"

    # Must have a call_id (voice call)
    if not conversation.call_id:
        return False, "No call_id (not a voice call)"

    return True, "Conversation is meaningful"


async def track_conversation_usage_to_stripe(
    session: AsyncSession,
    call_id: str,
    project: db.Project,
    timestamp: Optional[datetime] = None,
) -> bool:
    """
    Track conversation usage to Stripe based on conversation data (source of truth).

    This function reports usage to Stripe based on the conversation stored in the
    database rather than raw VAPI data, ensuring conversations table is the
    single source of truth for billing.

    Args:
        session: Database session
        call_id: Call ID to look up conversation
        project: Project object containing account and stripe customer info
        timestamp: Optional timestamp to use for the meter event (defaults to conversation.updated_at)

    Returns:
        bool: True if successfully reported to Stripe, False otherwise
    """
    try:
        # Query the conversation from database (source of truth) using repository
        conversation_repo = ConversationRepositoryAsync(session)
        conversation = await conversation_repo.get_conversation_by_call_id(
            call_id=call_id
        )

        if not conversation:
            logger.warning(
                "Conversation not found in database for usage tracking",
                extra={
                    "call_id": call_id,
                    "project_id": str(project.id),
                },
            )
            return False

        # Check if conversation is meaningful for billing
        is_meaningful, reason = _is_conversation_meaningful(conversation)
        if not is_meaningful:
            logger.info(
                f"Conversation not meaningful for billing: {reason}",
                extra={
                    "call_id": call_id,
                    "conversation_id": str(conversation.id),
                    "project_id": str(project.id),
                    "reason": reason,
                },
            )
            return False

        # Get stripe_customer_id
        stripe_customer_id = project.account.stripe_customer_id
        if not stripe_customer_id:
            logger.info(
                "No Stripe customer ID found - skipping usage tracking",
                extra={
                    "call_id": call_id,
                    "conversation_id": str(conversation.id),
                    "project_id": str(project.id),
                },
            )
            return False

        # Generate event name
        event_name = get_call_meter_event_name(project.id)

        # Use provided timestamp or conversation's updated_at
        event_timestamp = timestamp or conversation.updated_at

        # Report to Stripe (synchronous call)
        success = send_meter_event(
            event_name=event_name,
            stripe_customer_id=stripe_customer_id,
            value=1,
            timestamp=event_timestamp,
        )

        if success:
            logger.info(
                "Successfully reported conversation usage to Stripe",
                extra={
                    "call_id": call_id,
                    "conversation_id": str(conversation.id),
                    "project_id": str(project.id),
                },
            )
        else:
            logger.info(
                "Failed to report conversation usage to Stripe",
                extra={
                    "call_id": call_id,
                    "conversation_id": str(conversation.id),
                    "project_id": str(project.id),
                },
            )

        return success

    except Exception as e:
        logger.error(
            f"Error tracking conversation usage: {e}",
            extra={
                "call_id": call_id,
                "project_id": str(project.id),
            },
            exc_info=True,
        )
        return False
