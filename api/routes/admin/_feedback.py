import os
import re
import uuid
from collections import defaultdict
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import db
from api.schemas.admin.feedback import (
    CreateFeedbackRequest,
    Feedback,
    FeedbackDetail,
    ListFeedbacksResponse,
    UpdateFeedbackRequest,
)
from services import (
    account_service,
    feedback_service,
    message_service,
    notion_service,
    postmark_service,
    slack_service,
    user_service,
)
from services.auth_service import check_permission
from services.auth_types import UserRole
from utils.log import logger

from . import UserContext, _builder
from ._utils import not_found_error


def _check_account_access(context: UserContext, account, session: Session) -> None:
    """Check if user has access to the account using RBAC."""
    # Admin has full access
    if context.role == UserRole.Admin:
        return
    # Check permission on account
    user_id = UUID(context.username)
    if not check_permission(user_id, f"accounts/{account.id}", "account.read", session):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing required permission: account.read",
            headers={"Content-Type": "application/json"},
        )


async def list_account_feedbacks(
    account_name: str,
    context: UserContext,
    session: Session,
) -> ListFeedbacksResponse:
    """
    To get the feedbacks for the given account, it's a long journey.
    TODO (frankie.liu): add an account foreign key relation in feedback
    to make it simpler.
    Authorization is handled by require_account_permission in route decorator.
    """
    default_page = 1
    max_conversations_to_search = 1000
    # Validate account first
    account = account_service.get_account(session, account_name)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_name} not found.",
            headers={"Content-Type": "application/json"},
        )

    # Get all conversations in this account
    account_users = user_service.get_users_by_account_id(session, account.id)
    account_users_ids = [user.id for user in account_users]
    _, account_conversations = message_service.get_conversations_by_users(
        session, default_page, max_conversations_to_search, account_users_ids
    )
    conversation_ids = set([conversation.id for conversation in account_conversations])

    # Get all conversations that have feedbacks regardless of account
    feedbacks = feedback_service.get_feedbacks(session)
    if not feedbacks:
        logger.debug("No feedbacks found!")
        return ListFeedbacksResponse(feedbacks=[])
    msg_id_to_feedbacks = defaultdict(list)
    for feedback in feedbacks:
        msg_id_to_feedbacks[feedback.message_id].append(feedback)
    message_ids = list(msg_id_to_feedbacks)
    feedback_messages = message_service.get_messages_by_ids(session, message_ids)
    feedback_messages_dict = {msg.id: msg for msg in feedback_messages}

    # Pick feedbacks where the message belongs to one of the conversations in
    # this account
    account_feedbacks = []
    for message in feedback_messages:
        if message.conversation_id in conversation_ids:
            account_feedbacks.extend(msg_id_to_feedbacks[message.id])

    logger.debug(
        f"Found {len(account_feedbacks)} feedbacks for account {account_name}",
        extra={
            "users_in_account": len(account_users_ids),
            "conversations_in_account": len(conversation_ids),
            "total_feedbacks": len(feedbacks),
            "total_messages_w_feedback": len(feedback_messages_dict),
        },
    )
    # Finally sort the feedbacks in reverse-chronological order based on the
    # creation time.
    sorted_feedbacks = sorted(
        account_feedbacks, key=lambda f: f.created_at, reverse=True
    )
    # Build the feedback detail list
    detailed_feedbacks = []
    for feedback in sorted_feedbacks:
        message = feedback_messages_dict[feedback.message_id]
        detailed_feedbacks.append(
            FeedbackDetail(
                feedback=_builder.build_feedback(feedback, message),
                conversation_id=message.conversation_id,
            )
        )
    return ListFeedbacksResponse(feedbacks=detailed_feedbacks)


async def retrieve_feedback_by_id(
    feedback_id: uuid.UUID, context: UserContext, session: Session
) -> FeedbackDetail:
    """Authorization handled by require_feedback_permission in route decorator."""
    feedback = feedback_service.get_feedback_by_id(session, feedback_id)
    if not feedback:
        raise not_found_error(f"Feedback not found for id: {feedback_id}")
    conversation = feedback.message.conversation

    return FeedbackDetail(
        feedback=_builder.build_feedback(feedback),
        conversation_id=conversation.id,
    )


async def create_feedback(
    feedback_create: CreateFeedbackRequest,
    context: UserContext,
    session: Session,
) -> Feedback:
    """
    Create feedback and trigger integrations (Notion, Slack, Email).

    Workflow:
    1. Save feedback to SQL database (fire-and-forget logging)
    2. Create Notion ticket in Feedback Inbox
    3. Send receipt email to user (immediate confirmation)
    4. Send Slack notification with interactive buttons (for FDE triage)

    Note: All integrations are fire-and-forget. If any external service fails,
    we log the error but still return 200 OK to avoid user-facing errors.
    """
    # Validate & authorize feedback create request
    message = message_service.get_message_by_id(session, feedback_create.message_id)
    if not message:
        raise not_found_error(f"Message {feedback_create.message_id} does not exist.")
    account = message.conversation.user.account
    conversation = message.conversation
    _check_account_access(context, account, session)

    # Save to SQL database (fire-and-forget logging)
    feedback = _to_db_feedback(feedback_create)
    feedback.author_identifier = context.email
    feedback.author_name = context.display_name or None
    feedback.message_id = feedback_create.message_id
    persisted_feedback = feedback_service.create_feedback(session, feedback)

    logger.info(
        "[Feedback] Created feedback record in database",
        extra={
            "feedback_id": str(persisted_feedback.id),
            "conversation_id": str(conversation.id),
            "account": account.name,
        },
    )

    # Build conversation link with full URL
    console_base = os.environ.get(
        "PAL_CONSOLE_BASE_URL", "https://lat-console.palona.ai"
    )

    conversation_link = (
        f"{console_base}/hosting/conversations?conversationId={conversation.id}"
    )

    # Create Notion ticket
    notion_ticket_url = None
    notion_page_id = None
    try:
        notion_ticket_url = await notion_service.create_feedback_ticket(
            client_name=account.name,
            user_name=context.display_name or context.email,
            feedback_text=persisted_feedback.note,
            conversation_link=conversation_link,
            conversation_id=str(conversation.id),
            tags=persisted_feedback.tags,
            reaction=persisted_feedback.reaction,
            user_email=context.email,
        )

        if notion_ticket_url:
            # Extract Notion page ID from URL for Slack button payload
            notion_page_id = _extract_notion_page_id(notion_ticket_url)
            if notion_page_id:
                logger.info(
                    "[Feedback] Created Notion ticket and extracted page ID",
                    extra={
                        "feedback_id": str(persisted_feedback.id),
                        "notion_url": notion_ticket_url,
                        "notion_page_id": notion_page_id,
                    },
                )
            else:
                logger.warning(
                    "[Feedback] Created Notion ticket but failed to extract page ID from URL",
                    extra={
                        "feedback_id": str(persisted_feedback.id),
                        "notion_url": notion_ticket_url,
                    },
                )
        else:
            logger.warning("[Feedback] Notion ticket creation returned None")
    except Exception as e:
        logger.error(
            f"[Feedback] Error creating Notion ticket: {e}",
            extra={"feedback_id": str(persisted_feedback.id)},
            exc_info=True,
        )

    # Send receipt email using PostMark (resilient - errors are logged but don't fail request)
    try:
        email_sent = await postmark_service.send_feedback_receipt(
            user_email=context.email,
            user_name=context.display_name or context.email or "Valued Customer",
            feedback_text=persisted_feedback.note or "",
        )
        # Extract email domain for logging (avoid PII exposure)
        email_domain = (
            context.email.split("@")[-1] if "@" in context.email else "unknown"
        )
        if email_sent:
            logger.info(
                "[Feedback] Sent receipt email",
                extra={"email_domain": email_domain},
            )
        else:
            logger.warning(
                "[Feedback] Receipt email not sent",
                extra={"email_domain": email_domain},
            )
    except Exception as e:
        logger.error(
            f"[Feedback] Error sending receipt email: {e}",
            exc_info=True,
        )

    # Send Slack notification with interactive buttons (resilient)
    try:
        client_channel = slack_service.get_feedback_channel_for_client(account.name)
        slack_result = await slack_service.send_feedback_notification(
            client_name=account.name,
            user_email=context.email,
            user_name=context.display_name,
            tags=persisted_feedback.tags,
            feedback_text=persisted_feedback.note,
            conversation_id=str(conversation.id),
            conversation_link=conversation_link,
            notion_ticket_url=notion_ticket_url,
            notion_page_id=notion_page_id,
            reaction=persisted_feedback.reaction,
            feedback_id=str(persisted_feedback.id),
            channel_override=client_channel,
        )
        if slack_result:
            logger.info(
                "[Feedback] Sent Slack notification",
                extra={
                    "feedback_id": str(persisted_feedback.id),
                    "channel": client_channel or "default",
                    "message_ts": slack_result.get("ts"),
                },
            )
        else:
            logger.warning("[Feedback] Slack notification not sent")
    except Exception as e:
        logger.error(
            f"[Feedback] Error sending Slack notification: {e}",
            extra={"feedback_id": str(persisted_feedback.id)},
            exc_info=True,
        )

    # Return the created feedback (always succeeds even if integrations fail)
    return _builder.build_feedback(persisted_feedback)


def _extract_notion_page_id(notion_url: str) -> Optional[str]:
    """
    Extract Notion page ID from URL.

    Notion URLs format: https://www.notion.so/Title-{page_id}?...
    Example: https://www.notion.so/Feedback-Client-A-2ee7e6e39cdc8157bd28fc1f8f085f3c

    The page ID is always the last 32 hex characters (no dashes).

    Args:
        notion_url: The Notion page URL

    Returns:
        str: The page ID (32 hex chars without dashes), or None if extraction fails

    Examples:
        >>> _extract_notion_page_id("https://www.notion.so/Feedback-Client-A-2ee7e6e39cdc8157bd28fc1f8f085f3c")
        '2ee7e6e39cdc8157bd28fc1f8f085f3c'
    """
    try:
        parts = notion_url.split("/")
        if len(parts) > 0:
            page_id_part = parts[-1].split("?")[0]

            if len(page_id_part) >= 32:
                page_id = page_id_part[-32:]
                try:
                    int(page_id, 16)
                    logger.debug(
                        "[Feedback] Successfully extracted Notion page ID",
                        extra={
                            "notion_url": notion_url,
                            "page_id": page_id,
                        },
                    )
                    return page_id
                except ValueError:
                    match = re.search(r"([a-f0-9]{32})", page_id_part.lower())
                    if match:
                        return match.group(1)

        logger.warning(
            "[Feedback] Could not extract valid 32-character hex page ID from URL",
            extra={"notion_url": notion_url},
        )
        return None

    except Exception as e:
        logger.warning(
            f"[Feedback] Failed to extract Notion page ID from URL: {e}",
            extra={"notion_url": notion_url},
        )
        return None


async def update_feedback(
    feedback_id: uuid.UUID,
    feedback_update: UpdateFeedbackRequest,
    context: UserContext,
    session: Session,
):
    """Authorization handled by require_feedback_permission in route decorator."""
    curr_feedback = feedback_service.get_feedback_by_id(session, feedback_id)
    if not curr_feedback:
        raise not_found_error(f"Feedback {feedback_id} not found.")

    # Process update
    new_feedback = _to_db_feedback(feedback_update)
    updated_feedback = feedback_service.update_feedback_by_id(
        session, feedback_id, new_feedback
    )
    return _builder.build_feedback(updated_feedback)


async def delete_feedback(
    feedback_id: uuid.UUID,
    context: UserContext,
    session: Session,
):
    """Authorization handled by require_feedback_permission in route decorator."""
    curr_feedback = feedback_service.get_feedback_by_id(session, feedback_id)
    if not curr_feedback:
        # If feedback doesn't exist, this is a no-op, and it shouldn't
        # fail the request.
        return

    # Process delete
    feedback_service.delete_feedback_by_id(session, feedback_id)


def _to_db_feedback(feedback: UpdateFeedbackRequest) -> db.Feedback:
    return db.Feedback(
        author_identifier=feedback.author_identifier,
        reaction=feedback.reaction.value if feedback.reaction else None,
        tags=([tag.value for tag in feedback.tags] if feedback.tags else None),
        note=feedback.note,
    )
