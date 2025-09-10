import os
from datetime import datetime

from fastapi import HTTPException, Response, status
from sqlalchemy.orm import Session

from api.schemas.admin.account import (
    Account,
    AccountStatisticsResponse,
    AccountStatusResponse,
    CreateAccountRequest,
    ListAccountsResponse,
    TermsStatusResponse,
    UpdateAccountRequest,
)
from api.schemas.admin.agent import AgentSummary
from api.schemas.admin.user import SignUpRequest
from db import ConversationStatus
from db.tables.accounts import AccountStatus
from services import account_service, admin_service, subscription_service, user_service
from services.account_service import AccountParams
from services.admin_service.schema import CognitoUserSession
from utils.log import logger

from ._auth import authorize_user_account
from ._builder import build_account, build_account_summary, build_agent_summary
from ._utils import UserContext, create_guest_context, not_found_error

AWS_ADMIN_CONSOLE_APP_CLIENT_ID = os.environ["AWS_ADMIN_CONSOLE_APP_CLIENT_ID"]


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
            session=session,
            context=context,
            account_name=create_request.name,
            params=account_params,
            lead_id=create_request.lead_id,
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

    account = account_service.get_account(session, account_name)
    if not account:
        return

    curr_sub, _ = subscription_service.get_account_subscriptions(session, account.id)
    if curr_sub:
        raise ValueError("Account has active subscription and cannot be deleted.")

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
    start_date: datetime,
    end_date: datetime,
    context: UserContext,
    session: Session,
):
    authorize_user_account(context, account_name)
    account = account_service.get_account(session, account_name)
    if not account:
        raise not_found_error(f"Account {account_name} not found.")

    users = user_service.get_users_by_account_id(session, account.id, start_date)
    user_ids = [user.id for user in users]
    escalated_sessions = admin_service.get_escalated_session_count_by_users(
        session, user_ids, start_date, end_date
    )
    total_sessions = admin_service.get_session_count_by_user_and_status(
        session, user_ids, start_date, end_date
    )
    active_sessions = admin_service.get_session_count_by_user_and_status(
        session, user_ids, start_date, end_date, ConversationStatus.ACTIVE
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

    return [
        build_agent_summary(agent)
        for agent in sorted(account.agents, key=lambda a: a.created_at)
    ]


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


def get_account_terms_status(
    account_name: str,
    context: UserContext,
    session: Session,
) -> TermsStatusResponse:
    authorize_user_account(context, account_name)
    account = account_service.get_account(session, account_name)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_name} not found",
            headers={"Content-Type": "application/json"},
        )
    return TermsStatusResponse(
        id=account.id,
        name=account.name,
        terms_accepted=account.terms_accepted,
        display_name=account.display_name,
    )


async def user_signup(
    request: SignUpRequest, response: Response, session: Session
) -> AccountStatusResponse:
    """
    Sign up a new user and create an account. This function first creates an account
    with the given account_name, then creates a Cognito user. If Cognito user creation
    fails, the account is hard deleted to maintain consistency.

    Args:
        request: A SignUpRequest object containing the user's email, password, and account name.
        response: FastAPI response object for setting cookies.
        session: Database session for account operations.

    Returns:
        A SignUpResponse object containing the access token, refresh token,
        expiration time, and ID token for the newly created user.
    Raises:
        HTTPException: If there is an error signing up the user or creating the account.
    """
    # Create a guest context for account creation (no authenticated user yet)
    account_name = request.account_name
    guest_context = create_guest_context(account_name, request.email)

    try:
        account_service.create_account(
            session=session,
            context=guest_context,
            account_name=account_name,
            params=AccountParams(),
            lead_id=request.lead_id,
            auto_commit=False,  # Don't commit yet, in case Cognito creation fails
        )
        logger.info(f"Created account {account_name} for user signup")
    except ValueError as e:
        logger.error(f"Failed to create account {account_name}: {e}")
        raise ValueError(f"Failed to create account {account_name}: {e}") from e

    try:
        user = admin_service.signup_account_user(
            account_name=request.account_name,
            user_email=request.email,
            user_name=request.name,
            password=request.password,
        )
    except ValueError as e:
        # undo the account creation
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    if not user.session:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fully create user session",
            headers={"Content-Type": "application/json"},
        )
    session.commit()
    _set_user_session(response, user.email, user.session)
    return get_account_status(account_name, guest_context, session)


def _set_user_session(
    response: Response, user_email: str, user_session: CognitoUserSession
):
    # Set cookies
    client_id = AWS_ADMIN_CONSOLE_APP_CLIENT_ID
    user_sub = user_session.user_sub
    cookie_prefix = f"CognitoIdentityServiceProvider.{client_id}.{user_sub}"
    cookie_configs = {
        "httponly": False,
        "secure": True,
        "samesite": "lax",
    }
    signin_details = (
        f"{{%22loginId%22:%22{user_email}%22%2C%22authFlowType%22:%22USER_SRP_AUTH%22}}"
    )
    response.set_cookie(
        f"{cookie_prefix}.accessToken", user_session.access_token, **cookie_configs
    )
    response.set_cookie(
        f"{cookie_prefix}.idToken", user_session.id_token, **cookie_configs
    )
    response.set_cookie(
        f"{cookie_prefix}.refreshToken", user_session.refresh_token, **cookie_configs
    )
    response.set_cookie(
        f"{cookie_prefix}.signinDetails", signin_details, **cookie_configs
    )
    response.set_cookie(
        f"CognitoIdentityServiceProvider.{client_id}.LastAuthUser",
        user_sub,
        **cookie_configs,
    )


async def close_account(
    account_name: str,
    context: UserContext,
    session: Session,
):
    authorize_user_account(context, account_name)

    account = account_service.get_account(session, account_name)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_name} not found",
            headers={"Content-Type": "application/json"},
        )

    try:
        account_params = AccountParams(status=AccountStatus.disabled)
        account_service.update_account(session, context, account_name, account_params)
        logger.info(f"Successfully closed account {account_name}")
        return {"message": f"Account {account_name} has been successfully closed"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update account status: {str(e)}",
            headers={"Content-Type": "application/json"},
        )
