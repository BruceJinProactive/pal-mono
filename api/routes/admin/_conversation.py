import datetime
import math
import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from api.schemas.admin.conversation import (
    ListConversationMessagesResponse,
    ListUserSessionsResponse,
    UpdateConversationRequest,
    UserSessionSearchFilters,
)
from db.tables.types import Channel
from services import account_service, admin_service

from . import _builder
from ._auth import authorize_user_account
from ._utils import SortOrder, UserContext, not_found_error


async def list_account_conversations(
    account_name: str,
    keyword: str,
    channel: Channel | None,
    project_id: uuid.UUID | None,
    lookback: int | None,
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

    if lookback:
        start_date = datetime.datetime.now() - datetime.timedelta(seconds=lookback)
    else:
        start_date = None
    end_date = datetime.datetime.now()
    total, user_session_previews = admin_service.list_conversations_in_account(
        account_id=account.id,
        keyword=keyword,
        channel=channel.value if channel else None,
        project_id=project_id,
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
        _builder.build_conversation(
            conversation=preview.conversation,
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
    account_name: str | None,
    conversation_id: uuid.UUID,
    page: int,
    page_size: int,
    sort_order: SortOrder,
    context: UserContext,
    session: Session,
) -> ListConversationMessagesResponse:
    # Validate request
    if account_name:
        authorize_user_account(context, account_name)

    conversation = admin_service.get_conversation_by_id(session, conversation_id)
    if not conversation:
        raise not_found_error(f"Conversation not found for id: {conversation_id}")
    account = conversation.user.account

    if account_name and account_name != account.name:
        raise not_found_error(f"Conversation not found for id: {conversation_id}")

    if not account_name:
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


async def update_conversation(
    context: UserContext,
    session: Session,
    account_name: str,
    conversation_id: uuid.UUID,
    update_request: UpdateConversationRequest,
):
    authorize_user_account(context, account_name)

    # Fetch first to validate ownership
    conversation = admin_service.get_conversation_by_id(session, conversation_id)

    if not conversation:
        raise not_found_error(f"Conversation {conversation_id} not found")

    if account_name != conversation.user.account.name:
        raise not_found_error(f"Conversation {conversation_id} not found")

    conversation = admin_service.update_conversation(
        session,
        conversation_id=conversation_id,
        is_escalated=update_request.is_escalated,
        project_id=update_request.project_id,
    )

    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update conversation {conversation_id}",
        )
