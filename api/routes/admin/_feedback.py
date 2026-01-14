import uuid
from collections import defaultdict
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
from services import account_service, feedback_service, message_service, user_service
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
    # Validate & authorize feedback create request
    message = message_service.get_message_by_id(session, feedback_create.message_id)
    if not message:
        raise not_found_error(f"Message {feedback_create.message_id} does not exist.")
    account = message.conversation.user.account
    _check_account_access(context, account, session)

    # Process create - store user's email in author_identifier
    feedback = _to_db_feedback(feedback_create)
    feedback.author_identifier = context.email
    feedback.author_name = context.display_name or None
    feedback.message_id = feedback_create.message_id
    persisted_feedback = feedback_service.create_feedback(session, feedback)
    return _builder.build_feedback(persisted_feedback)


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
