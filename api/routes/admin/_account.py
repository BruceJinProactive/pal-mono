from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from api.schemas.admin.account import (
    Account,
    AccountStatisticsResponse,
    CreateAccountRequest,
    ListAccountsResponse,
    UpdateAccountRequest,
)
from db import ConversationStatus
from db.tables.accounts import BusinessIndustry
from services import account_service, admin_service, user_service
from services.account_service import AccountParams

from ._auth import authorize_user_account
from ._builder import build_account
from ._utils import UserContext, UserRole, not_found_error


def list_accounts(
    context: UserContext,
    session: Session,
) -> ListAccountsResponse:
    if context.account_names:
        accounts = account_service.mget_accounts(
            session, account_names=context.account_names
        )
    elif context.role == UserRole.Admin:
        accounts = account_service.get_accounts(session)
    else:
        accounts = []

    response = ListAccountsResponse(
        accounts=[build_account(account) for account in accounts]
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
    account_params = _validate_and_parse_request(create_request)
    try:
        db_account = account_service.create_account(
            session, create_request.name, account_params
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
    account_params = _validate_and_parse_request(update_request)
    try:
        db_account = account_service.update_account(
            session, account_name, account_params
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
    context: UserContext,
    session: Session,
):
    authorize_user_account(context, account_name)
    account_service.delete_account(session, account_name)


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


def _validate_and_parse_request(update: UpdateAccountRequest) -> AccountParams:
    business_industry = None
    if update.industry:
        try:
            business_industry = BusinessIndustry(update.industry)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid industry value: {update.industry}",
                headers={"Content-Type": "application/json"},
            )
    return account_service.AccountParams(
        display_name=update.display_name,
        icon_uri=update.icon_uri,
        industry=business_industry,
        business_description=update.business_description,
        business_faq=update.business_faq,
        business_promotions=update.business_promotions,
        business_catalog=update.business_catalog,
        business_others=update.business_others,
    )
