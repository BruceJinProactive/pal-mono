import datetime
import math
import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from api.schemas.admin.conversation import (
    ListConversationMessagesResponse,
    ListUserSessionsResponse,
    UpdateSessionRequest,
    UpdateSessionResponse,
    UserSessionSearchFilters,
)
from api.schemas.chat.message import Channel
from services import account_service, admin_service

from . import _builder
from ._auth import authorize_user_account
from ._utils import SortOrder, UserContext, not_found_error


async def list_account_user_sessions(
    account_name: str,
    keyword: str,
    channel: Channel | None,
    lookback: int,
    page: int,
    page_size: int,
    escalated: bool,
    hide_testing_sessions: bool,
    context: UserContext,
    session: Session,
) -> ListUserSessionsResponse:
    authorize_user_account(context, account_name)
    account = account_service.get_account(session, account_name)
    if not account:
        raise not_found_error(f"Account {account_name} not found")

    start_date = datetime.datetime.now() - datetime.timedelta(seconds=lookback)
    end_date = datetime.datetime.now()
    total, user_session_previews = admin_service.list_user_sessions_in_account(
        account_id=account.id,
        keyword=keyword,
        channel=channel.value if channel else None,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
        escalated=escalated,
        hide_testing_sessions=hide_testing_sessions,
        db_session=session,
    )
    total_pages = (total + page_size - 1) // page_size

    user_sessions = [
        _builder.build_user_session(
            user_session=preview.user_session,
            last_message=preview.last_message,
            message_count=preview.message_count,
        )
        for preview in user_session_previews
    ]

    return ListUserSessionsResponse(
        sessions=user_sessions,
        filters=UserSessionSearchFilters(
            channels=[channel.value for channel in Channel]
        ),
        total_sessions=total,
        total_pages=total_pages,
    )


async def list_conversation_messages(
    conversation_id: uuid.UUID,
    page: int,
    page_size: int,
    sort_order: SortOrder,
    context: UserContext,
    session: Session,
) -> ListConversationMessagesResponse:
    # Validate request
    conversation = admin_service.get_conversation_by_id(session, conversation_id)
    if not conversation:
        raise not_found_error(f"Conversation not found for id: {conversation_id}")
    account = conversation.user.account
    authorize_user_account(context, account.name)

    # Retrieve conversation messages
    all_messages = admin_service.get_conversation_messages(
        session, account.id, conversation_id, sort_desc=(sort_order == SortOrder.desc)
    )

    # Paginate response
    total_messages = len(all_messages)
    total_pages = math.ceil(total_messages / page_size)
    start = (page - 1) * page_size
    end = start + page_size
    selected_messages = all_messages[start:end]

    return ListConversationMessagesResponse(
        messages=[_builder.build_message(msg) for msg in selected_messages],
        total_pages=total_pages,
        total_messages=total_messages,
    )


async def update_session(
    session_id: uuid.UUID,
    session_request: UpdateSessionRequest,
    context: UserContext,
    session: Session,
) -> UpdateSessionResponse:
    """Update session escalation status.

    Args:
        session_id: The ID of the session to update
        session_request: The update request containing is_escalated flag
        context: The authenticated user context
        session: The database session

    Returns:
        UpdateSessionResponse: The response containing the updated escalation status

    Raises:
        HTTPException: If the session is not found or user is not authorized
    """
    # Fetch first to validate ownership
    conversation = admin_service.get_conversation_by_id(session, session_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    # Authorize user has access to this account
    authorize_user_account(context, conversation.user.account.name)

    # Safe to mutate after successful auth
    conversation = admin_service.update_conversation_escalation(
        session, session_id, session_request.is_escalated
    )

    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Failed to update session {session_id}",
        )

    return UpdateSessionResponse(is_escalated=conversation.is_escalated)
