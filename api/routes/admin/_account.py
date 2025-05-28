from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from api.schemas.admin.account import (
    Account,
    AccountStatisticsResponse,
    AccountStatusResponse,
    CreateAccountRequest,
    ListAccountsResponse,
    UpdateAccountRequest,
)
from api.schemas.admin.agent import AgentSummary
from db import ConversationStatus
from services import account_service, admin_service, user_service

from ._auth import authorize_user_account
from ._builder import build_account, build_account_summary, build_agent_summary
from ._utils import UserContext, not_found_error


def list_accounts(
    context: UserContext,
    session: Session,
    keyword: str | None = None,
) -> ListAccountsResponse:
    accounts = account_service.filter_accounts_by_name(session, keyword=keyword)

    response = ListAccountsResponse(
        accounts=[build_account_summary(account) for account in accounts]
    )
    return response


def get_account(
    account_name: str,
    context: UserContext,
    session: Session,
) -> Account:
    authorize_user_account(context, account_name)
    account = account_service.get_account(session, account_name)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_name} not found",
            headers={"Content-Type": "application/json"},
        )
    return build_account(account)


async def create_account(
    create_request: CreateAccountRequest,
    context: UserContext,
    session: Session,
) -> Account:
    authorize_user_account(context, create_request.name)
    account_params = create_request.to_account_params()
    try:
        db_account = account_service.create_account(
            session, context, create_request.name, account_params
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
            headers={"Content-Type": "application/json"},
        )
    return build_account(db_account)


async def update_account(
    account_name: str,
    update_request: UpdateAccountRequest,
    context: UserContext,
    session: Session,
) -> Account:
    authorize_user_account(context, account_name)
    account_params = update_request.to_account_params()
    try:
        db_account = account_service.update_account(
            session, context, account_name, account_params
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
            headers={"Content-Type": "application/json"},
        )
    return build_account(db_account)


async def delete_account(
    account_name: str,
    hard_delete: bool,
    context: UserContext,
    session: Session,
):
    authorize_user_account(context, account_name)
    try:
        account_service.delete_account(session, account_name, hard_delete, context)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )


async def get_account_statistics(
    account_name: str,
    lookback: int,
    context: UserContext,
    session: Session,
):
    authorize_user_account(context, account_name)
    account = account_service.get_account(session, account_name)
    if not account:
        raise not_found_error(f"Account {account_name} not found.")
    if lookback:
        min_create_time = datetime.now() - timedelta(seconds=lookback)
    else:
        min_create_time = datetime.min

    users = user_service.get_users_by_account_id(session, account.id, min_create_time)
    user_ids = [user.id for user in users]
    escalated_sessions = admin_service.get_escalated_session_count_by_users(
        session, user_ids, min_create_time
    )
    total_sessions = admin_service.get_session_count_by_user_and_status(
        session, user_ids, min_create_time
    )
    active_sessions = admin_service.get_session_count_by_user_and_status(
        session, user_ids, min_create_time, ConversationStatus.ACTIVE
    )
    return AccountStatisticsResponse(
        total_users=len(user_ids),
        total_sessions=total_sessions,
        active_sessions=active_sessions,
        escalated_sessions=escalated_sessions,
    )


async def list_account_agents(
    account_name: str,
    context: UserContext,
    session: Session,
) -> list[AgentSummary]:
    authorize_user_account(context, account_name)

    account = account_service.get_account(session, account_name)
    if not account:
        raise not_found_error(f"Account {account_name} not found")

    return [build_agent_summary(agent) for agent in account.agents]


def get_account_status(
    account_name: str,
    context: UserContext,
    session: Session,
) -> AccountStatusResponse:
    authorize_user_account(context, account_name)
    account = account_service.get_account(session, account_name)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_name} not found",
            headers={"Content-Type": "application/json"},
        )
    return AccountStatusResponse(
        id=account.id,
        name=account.name,
        status=account.status,
        display_name=account.display_name,
    )
