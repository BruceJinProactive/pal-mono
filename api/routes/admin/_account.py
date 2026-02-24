import math
import os
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, Response, status
from sqlalchemy import exc as sqlalchemy_exc
from sqlalchemy.orm import Session

from api.schemas.admin.account import (
    AcceptTermsRequest,
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
from db import AccountRepository, ConversationStatus, TosAcceptanceRepository
from db.tables.accounts import AccountStatus
from db.tables.types import SubscriptionStatus
from services import (
    account_service,
    admin_service,
    subscription_service,
    terms_service,
    user_service,
)
from services.account_service import AccountParams
from services.admin_service.schema import CognitoUserSession
from services.auth_service.authorization import get_user_role_on_account
from utils.log import logger

from ._builder import build_account, build_account_summary, build_agent_summary
from ._utils import UserContext, not_found_error

AWS_ADMIN_CONSOLE_APP_CLIENT_ID = os.environ["AWS_ADMIN_CONSOLE_APP_CLIENT_ID"]


def list_accounts(
    context: UserContext,
    session: Session,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
    status: list[AccountStatus] | None = None,
    subscription_status: list[SubscriptionStatus] | None = None,
) -> ListAccountsResponse:
    accounts, total = account_service.filter_accounts(
        session,
        keyword=keyword,
        page=page,
        page_size=page_size,
        status=status,
        subscription_status=subscription_status,
        load_subscription=True,
    )

    total_pages = math.ceil(total / page_size) if total > 0 else 0
    return ListAccountsResponse(
        accounts=[build_account_summary(account) for account in accounts],
        total=total,
        total_pages=total_pages,
        page=page,
        page_size=page_size,
    )


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

    # Get current TOS version from environment (default to v1.0 if not set)
    current_tos_version = os.environ.get("CURRENT_TOS_VERSION", "v1.0")

    return TermsStatusResponse(
        id=account.id,
        name=account.name,
        terms_accepted=account.terms_accepted,
        display_name=account.display_name,
        current_tos_version=current_tos_version,
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
    request: AcceptTermsRequest,
    context: UserContext,
    session: Session,
) -> AcceptTermsResponse:
    # Server-side validation (frontend validation is UX only)
    normalized_email = (context.email or "").strip().lower()
    if normalized_email.endswith("@proactiveailab.com"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Users with @proactiveailab.com emails are not allowed to accept Terms of Service.",
            headers={"Content-Type": "application/json"},
        )

    account = account_service.get_account(session, account_name)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_name} not found",
            headers={"Content-Type": "application/json"},
        )

    try:
        user_id = uuid.UUID(context.username)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication context (missing user id).",
            headers={"Content-Type": "application/json"},
        ) from e

    # Only allow account Owner role to accept (not Manager/Viewer)
    role = get_user_role_on_account(
        user_id=user_id, account_id=account.id, session=session
    )
    if role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only account Owners can accept Terms of Service.",
            headers={"Content-Type": "application/json"},
        )

    accepted_at = datetime.now(UTC)

    # Update account flag (existing behavior)
    account_params = AccountParams(terms_accepted=True)
    try:
        account_service.update_account(session, context, account_name, account_params)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
            headers={"Content-Type": "application/json"},
        )

    # Create TOS acceptance record (idempotent)
    tos_repo = TosAcceptanceRepository(session)

    # Check if this TOS version has already been accepted
    existing_acceptance = tos_repo.get_tos_acceptance_by_version(
        account_id=account.id, tos_version=request.tos_version
    )

    if not existing_acceptance:
        # Only create if not already accepted
        try:
            tos_repo.create_tos_acceptance(
                account_id=account.id,
                display_name=account.display_name or account.name,
                tos_version=request.tos_version,
                user_id=user_id,
                user_email=normalized_email,
                accepted_at=accepted_at,
            )
        except sqlalchemy_exc.IntegrityError as err:
            # Race condition: another request already created this record
            # Roll back and re-check to confirm the record exists
            session.rollback()
            existing_acceptance = tos_repo.get_tos_acceptance_by_version(
                account_id=account.id, tos_version=request.tos_version
            )
            if not existing_acceptance:
                # Still doesn't exist - this is an unexpected integrity error
                logger.error(
                    f"IntegrityError for TOS acceptance but record not found for account {account_name}"
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to record TOS acceptance. Please try again.",
                    headers={"Content-Type": "application/json"},
                ) from err
            # Record exists, treat as idempotent success
            # Re-apply account update since rollback undid it
            try:
                account_service.update_account(
                    session, context, account_name, account_params
                )
            except ValueError as update_err:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(update_err),
                    headers={"Content-Type": "application/json"},
                ) from update_err
            logger.info(
                f"TOS acceptance already exists for account {account_name}, treating as idempotent success"
            )
        except Exception as e:
            # Roll back the entire transaction including the account update
            session.rollback()
            logger.error(
                f"Failed to record TOS acceptance for account {account_name}: {e}"
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to record TOS acceptance. Please try again.",
                headers={"Content-Type": "application/json"},
            ) from e

    # Explicitly commit the transaction (both account update and TOS acceptance)
    session.commit()

    return AcceptTermsResponse(accepted=True, tos_version=request.tos_version)


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


async def backfill_accounts_without_owners(
    context: UserContext,
    session: Session,
    dry_run: bool = False,
) -> dict:
    """
    Backfill accounts that have no owners with environment-specific default owners.

    For LAT: jacob+palona.lat@proactiveailab.com and kelvin+lat@proactiveailab.com
    For PRD: jacob+palona@proactiveailab.com and kelvin@proactiveailab.com

    Args:
        context: User context for authorization
        session: Database session
        dry_run: If True, only return what would be changed without making changes

    Returns:
        Dict containing accounts that would be/were updated and owners added
    """
    try:
        result = admin_service.backfill_accounts_without_owners(
            session=session,
            context=context,
            dry_run=dry_run,
        )
        return result
    except Exception as e:
        logger.error(f"Failed to backfill accounts without owners: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to backfill accounts: {str(e)}",
            headers={"Content-Type": "application/json"},
        )
