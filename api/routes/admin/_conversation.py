import math
import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from api.schemas.admin.conversation import (
    ListConversationMessagesResponse,
    ListConversationsResponse,
)
from services import account_service, admin_service

from . import _builder
from ._auth import authorize_user_account
from ._utils import UserContext, not_found_error


async def list_account_conversations(
    account_name: str,
    page: int,
    page_size: int,
    context: UserContext,
    session: Session,
) -> ListConversationsResponse:
    authorize_user_account(context, account_name)
    account = account_service.get_account(session, account_name)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_name} not found",
            headers={"Content-Type": "application/json"},
        )
    total, conversations = admin_service.get_inbox_conversations(
        session, account_id=account.id, page=page, page_size=page_size
    )
    total_pages = (total + page_size - 1) // page_size
    return ListConversationsResponse(
        conversations=conversations,
        total_conversations=total,
        total_pages=total_pages,
    )


async def list_conversation_messages(
    conversation_id: uuid.UUID,
    page: int,
    page_size: int,
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
        session, account.id, conversation_id
    )
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
