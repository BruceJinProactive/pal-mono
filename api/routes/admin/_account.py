import os
from datetime import UTC, datetime

from fastapi import HTTPException, Response, status
from sqlalchemy.orm import Session

from api.schemas.admin.account import (
    AcceptTermsResponse,
    Account,
    AccountStatisticsResponse,
    AccountStatusResponse,
    CreateAccountRequest,
    ListAccountsResponse,
    NotificationPreferences,
    NotificationPreferencesResponse,
    TermsStatusResponse,
    UpdateAccountRequest,
    UpdateNotificationPreferencesRequest,
)
from api.schemas.admin.agent import AgentSummary
from db import AccountRepository, ConversationStatus
from db.tables.accounts import AccountStatus
from services import (
    account_service,
    admin_service,
    subscription_service,
    terms_service,
    user_service,
)
from services.account_service import AccountParams
from services.admin_service.schema import CognitoUserSession
from utils.log import logger

from ._builder import build_account, build_account_summary, build_agent_summary
from ._utils import UserContext, not_found_error

AWS_ADMIN_CONSOLE_APP_CLIENT_ID = os.environ["AWS_ADMIN_CONSOLE_APP_CLIENT_ID"]


def list_accounts(
    context: UserContext,
    session: Session,
    keyword: str | None = None,
) -> ListAccountsResponse:
    accounts = account_service.filter_accounts_by_name(
        session, keyword=keyword, load_subscription=True
    )

    response = ListAccountsResponse(
        accounts=[build_account_summary(account) for account in accounts]
    )
    return response


def get_account(
    account_name: str,
    context: UserContext,
    session: Session,
) -> Account:
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
    account_params = update_request.to_account_params()
    try:
        db_account = account_service.update_account(
            session,
            context,
            account_name,
            account_params,
            update_request.expected_version,
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


async def initiate_terms_signing(
    account_name: str,
    signer_name: str,
    signer_email: str,
    redirect_url: str,
    frame_ancestors: list[str] | None,
    context: UserContext,
    session: Session,
) -> dict:
    """
    Initiate terms of service signing via DocuSign.
    Returns signing URL for embedded signing.
    """
    account = account_service.get_account(session, account_name)

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_name} not found",
            headers={"Content-Type": "application/json"},
        )

    if account.terms_accepted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Terms already accepted for account {account_name}",
            headers={"Content-Type": "application/json"},
        )

    try:
        result = terms_service.initiate_terms_signing(
            account=account,
            signer_name=signer_name,
            signer_email=signer_email,
            redirect_url=redirect_url,
            frame_ancestors=None,
        )

        account_repo = AccountRepository(session)
        updated = account_repo.update_account(
            account_name=account_name,
            terms_envelope_id=result["envelope_id"],
        )

        if not updated:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update account with envelope ID",
                headers={"Content-Type": "application/json"},
            )

        return {
            "success": True,
            "envelope_id": result["envelope_id"],
            "signing_url": result["signing_url"],
            "signer_client_user_id": result["signer_client_user_id"],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to initiate terms signing: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initiate terms signing. Please try again later.",
            headers={"Content-Type": "application/json"},
        )


async def complete_terms_signing(
    account_name: str,
    envelope_id: str,
    context: UserContext,
    session: Session,
) -> dict:
    """
    Mark terms as accepted after user completes signing.
    Frontend calls this after DocuSign JS fires 'signing_complete' event.
    """
    account = account_service.get_account(session, account_name)

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_name} not found",
            headers={"Content-Type": "application/json"},
        )

    if account.terms_envelope_id != envelope_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Envelope ID mismatch",
            headers={"Content-Type": "application/json"},
        )

    try:
        status_info = terms_service.get_envelope_status(envelope_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to verify envelope status with DocuSign",
            headers={"Content-Type": "application/json"},
        )

    if status_info.get("status") != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Envelope is not completed yet",
            headers={"Content-Type": "application/json"},
        )

    signed_at = datetime.now(UTC)
    account_repo = AccountRepository(session)
    updated_account = account_repo.update_account(
        account_name=account_name,
        terms_accepted=True,
        terms_signed_at=signed_at,
    )

    if not updated_account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_name} not found",
            headers={"Content-Type": "application/json"},
        )

    return {
        "success": True,
        "terms_accepted": updated_account.terms_accepted,
        "terms_signed_at": signed_at,
    }


async def accept_account_terms(
    account_name: str,
    context: UserContext,
    session: Session,
) -> AcceptTermsResponse:
    account_params = AccountParams(terms_accepted=True)
    try:
        account_service.update_account(session, context, account_name, account_params)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
            headers={"Content-Type": "application/json"},
        )
    return AcceptTermsResponse(accepted=True)


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


def get_notification_preferences(
    account_name: str,
    context: UserContext,
    session: Session,
) -> NotificationPreferencesResponse:
    """Get notification preferences for an account."""
    account = account_service.get_account(session, account_name)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_name} not found",
            headers={"Content-Type": "application/json"},
        )

    # Parse notification preferences JSONB field
    prefs = account.notification_preferences or {}
    notification_prefs = NotificationPreferences(
        email_enabled=prefs.get("email_enabled", True)
    )

    return NotificationPreferencesResponse(
        notification_preferences=notification_prefs,
        notification_email=account.notification_email,
    )


async def update_notification_preferences(
    account_name: str,
    update_request: UpdateNotificationPreferencesRequest,
    context: UserContext,
    session: Session,
) -> NotificationPreferencesResponse:
    """Update notification preferences for an account."""
    account = account_service.get_account(session, account_name)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_name} not found",
            headers={"Content-Type": "application/json"},
        )

    # Get current preferences
    current_prefs = account.notification_preferences or {}

    # Update preferences if provided
    if update_request.email_enabled is not None:
        current_prefs["email_enabled"] = update_request.email_enabled

    # Prepare account params
    account_params = AccountParams(
        notification_preferences=current_prefs,
        notification_email=(
            update_request.notification_email
            if update_request.notification_email is not None
            else account.notification_email
        ),
    )

    try:
        updated_account = account_service.update_account(
            session, context, account_name, account_params
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
            headers={"Content-Type": "application/json"},
        )

    # Return updated preferences
    notification_prefs = NotificationPreferences(
        email_enabled=updated_account.notification_preferences.get(
            "email_enabled", True
        )
    )

    return NotificationPreferencesResponse(
        notification_preferences=notification_prefs,
        notification_email=updated_account.notification_email,
    )
