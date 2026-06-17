import datetime
import math
import uuid
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from api.schemas.admin.conversation import (
    ConversationAccountLookupResponse,
    ListConversationMessagesResponse,
    ListUserSessionsResponse,
    OrderDetails,
    UpdateConversationRequest,
    UserSessionSearchFilters,
)
from db.tables.types import Channel
from services import account_service, admin_service
from services.auth_service.authorization import check_permission

from . import _builder
from ._utils import SortOrder, UserContext, not_found_error

OrderFilter = Literal["all", "paid", "unpaid"]


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
    language: list[str] | None,
    purpose: list[str] | None,
    ended_reason: list[str] | None,
    customer_converted: bool | None,
    context: UserContext,
    session: Session,
    has_order: bool | None = None,
    order_filter: OrderFilter | None = None,
    conversation_id: uuid.UUID | None = None,
) -> ListUserSessionsResponse:
    """Authorization is handled by require_account_permission in route decorator."""
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
        conversation_id=conversation_id,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
        escalated=escalated,
        hide_testing_sessions=hide_testing_sessions,
        language=language,
        purpose=purpose,
        ended_reason=ended_reason,
        customer_converted=customer_converted,
        has_order=has_order,
        order_filter=order_filter,
        db_session=session,
    )
    total_pages = (total + page_size - 1) // page_size

    user_sessions = [
        _builder.build_conversation(
            conversation=preview.conversation,
            last_message=preview.last_message,
            message_count=preview.message_count,
            order_number=preview.order_number,
            has_order=preview.has_order,
        )
        for preview in user_session_previews
    ]

    # Get distinct filter values for the account
    languages, purposes, ended_reasons = admin_service.get_conversation_filter_values(
        account.id, session
    )

    return ListUserSessionsResponse(
        sessions=user_sessions,
        filters=UserSessionSearchFilters(
            channels=[channel.value for channel in Channel],
            languages=languages,
            purposes=purposes,
            ended_reasons=ended_reasons,
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
    """Authorization is handled by require_account_permission in route decorator."""
    conversation = admin_service.get_conversation_by_id(session, conversation_id)
    if not conversation:
        raise not_found_error(f"Conversation not found for id: {conversation_id}")
    account = conversation.user.account

    if account_name and account_name != account.name:
        raise not_found_error(f"Conversation not found for id: {conversation_id}")

    # Retrieve conversation messages
    all_messages = admin_service.get_conversation_messages(
        session, account.id, conversation_id, sort_desc=(sort_order == SortOrder.desc)
    )

    # Filter out messages without displayable content (no text body and no media)
    all_messages = [
        msg
        for msg in all_messages
        if ((msg.body.get("text") or {}).get("body") or "").strip()
        or msg.body.get("media")
    ]

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


async def get_conversation_order_details(
    account_name: str,
    conversation_id: uuid.UUID,
    context: UserContext,
    session: Session,
) -> OrderDetails:
    """
    Get latest order details for a conversation.
    Authorization is handled by require_account_permission in route decorator.
    """
    conversation = admin_service.get_conversation_by_id(session, conversation_id)
    if not conversation:
        raise not_found_error(f"Conversation not found for id: {conversation_id}")

    account = conversation.user.account
    if account_name != account.name:
        raise not_found_error(f"Conversation not found for id: {conversation_id}")

    order = admin_service.get_conversation_order_details(session, conversation_id)
    if order is None:
        raise not_found_error(f"Order not found for conversation id: {conversation_id}")

    return _builder.build_order_details(order)


async def get_conversation_detail(
    account_name: str,
    conversation_id: uuid.UUID,
    context: UserContext,
    session: Session,
):
    """
    Get conversation details without messages.
    Authorization is handled by require_account_permission in route decorator.
    """
    conversation = admin_service.get_conversation_by_id(session, conversation_id)
    if not conversation:
        raise not_found_error(f"Conversation not found for id: {conversation_id}")

    account = conversation.user.account
    if account_name != account.name:
        raise not_found_error(f"Conversation not found for id: {conversation_id}")

    order_info = admin_service.get_conversation_order_display_info(
        session,
        conversation_id,
    )

    return _builder.build_conversation_detail(
        conversation,
        order_number=order_info.order_number,
        has_order=order_info.has_order,
    )


async def update_conversation(
    context: UserContext,
    session: Session,
    account_name: str,
    conversation_id: uuid.UUID,
    update_request: UpdateConversationRequest,
):
    """Authorization is handled by require_account_permission in route decorator."""
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


async def lookup_conversation_account(
    conversation_id: uuid.UUID,
    context: UserContext,
    session: Session,
) -> ConversationAccountLookupResponse:
    """Look up which account a conversation belongs to, verifying user access."""
    conversation = admin_service.get_conversation_by_id(session, conversation_id)
    if not conversation:
        raise not_found_error(f"Conversation not found for id: {conversation_id}")

    account = conversation.user.account
    account_name = account.name

    # Verify the user has read access to this account
    has_permission = check_permission(
        user_id=uuid.UUID(context.username),
        resource_id=f"accounts/{account_name}",
        permission_name="account.read",
        session=session,
        user_role=context.role.value,
    )
    if not has_permission:
        raise not_found_error(f"Conversation not found for id: {conversation_id}")

    return ConversationAccountLookupResponse(account_name=account_name)
