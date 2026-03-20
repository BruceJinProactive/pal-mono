import math
import os
import time
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
from db import ConversationStatus, TosAcceptanceRepository
from db.tables.accounts import AccountStatus
from db.tables.types import SubscriptionStatus
from services import account_service, admin_service, subscription_service, user_service
from services.account_service import AccountParams
from services.admin_service.schema import CognitoUserSession
from services.auth_service.authorization import get_user_role_on_account
from utils.dd import statsd
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

    # Get TOS status from tos_acceptances table only
    tos_status = account_service.get_tos_status(
        session, account.id, account_service.CURRENT_TOS_VERSION
    )

    return TermsStatusResponse(
        id=account.id,
        name=account.name,
        display_name=account.display_name,
        # TOS status from tos_acceptances table
        accepted_tos_version=tos_status["accepted_tos_version"],
        is_compliant=tos_status["is_compliant"],
        accepted_at=tos_status["accepted_at"],
        current_tos_version=account_service.CURRENT_TOS_VERSION,
    )


async def accept_account_terms(
    account_name: str,
    request: AcceptTermsRequest,
    context: UserContext,
    session: Session,
) -> AcceptTermsResponse:
    # Track acceptance flow duration and outcome
    start_time = time.time()
    outcome = "error"  # Default to error, update on success

    try:
        # Server-side validation (frontend validation is UX only)
        normalized_email = (context.email or "").strip().lower()

        # Fail fast if email is missing
        if not normalized_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User email is required to accept Terms of Service.",
                headers={"Content-Type": "application/json"},
            )

        if normalized_email.endswith(
            "@proactiveailab.com"
        ) or normalized_email.endswith("@palona.ai"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Internal team members are not allowed to accept Terms of Service.",
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

        # Validate TOS version matches current required version (before any updates)
        if request.tos_version != account_service.CURRENT_TOS_VERSION:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"TOS version mismatch. Client sent '{request.tos_version}' but server requires '{account_service.CURRENT_TOS_VERSION}'. Please refresh and try again.",
                headers={"Content-Type": "application/json"},
            )

        accepted_at = datetime.now(UTC)

        # No longer update account.terms_accepted field
        # The tos_acceptances table is the single source of truth for compliance

        # Create TOS acceptance record (idempotent)
        tos_repo = TosAcceptanceRepository(session)

        # Use shared constant for TOS version (single source of truth)
        tos_version = account_service.CURRENT_TOS_VERSION

        # Check if this TOS version has already been accepted
        try:
            existing_acceptance = tos_repo.get_tos_acceptance_by_version(
                account_id=account.id, tos_version=tos_version
            )
        except sqlalchemy_exc.SQLAlchemyError as db_err:
            # Database error during lookup - rollback and return error
            session.rollback()
            outcome = "error"
            logger.error(
                f"Database error checking TOS acceptance for account {account_name}: {db_err}",
                exc_info=True,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to check TOS acceptance status. Please try again.",
                headers={"Content-Type": "application/json"},
            ) from db_err

        if not existing_acceptance:
            # Only create if not already accepted
            try:
                tos_repo.create_tos_acceptance(
                    account_id=account.id,
                    display_name=account.display_name or account.name,
                    tos_version=tos_version,
                    user_id=user_id,
                    user_email=normalized_email,
                    accepted_at=accepted_at,
                )

                outcome = "created"

                # METRIC: Track successful TOS acceptance creation (best-effort)
                try:
                    statsd.increment(
                        "tos.acceptance.created", tags=[f"version:{tos_version}"]
                    )
                except Exception as metric_err:
                    logger.warning(
                        f"Failed to emit tos.acceptance.created metric: {metric_err}"
                    )

                logger.info(
                    f"TOS acceptance created for account {account_name} "
                    f"(version: {tos_version})"
                )
            except sqlalchemy_exc.IntegrityError as err:
                # Race condition: another request already created this record
                # Roll back and re-check to confirm the record exists
                session.rollback()

                try:
                    existing_acceptance = tos_repo.get_tos_acceptance_by_version(
                        account_id=account.id, tos_version=tos_version
                    )
                except sqlalchemy_exc.SQLAlchemyError as db_err:
                    # Database error during re-check after IntegrityError
                    outcome = "error"
                    logger.error(
                        f"Database error re-checking TOS acceptance after IntegrityError for account {account_name}: {db_err}",
                        exc_info=True,
                    )
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Failed to verify TOS acceptance. Please try again.",
                        headers={"Content-Type": "application/json"},
                    ) from db_err

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
                # PHASE 1: No longer re-apply account.terms_accepted update
                # The tos_acceptances table is the single source of truth

                outcome = "duplicate"

                # METRIC: Track duplicate acceptance attempts (best-effort)
                try:
                    statsd.increment(
                        "tos.acceptance.duplicate", tags=[f"version:{tos_version}"]
                    )
                except Exception as metric_err:
                    logger.warning(
                        f"Failed to emit tos.acceptance.duplicate metric: {metric_err}"
                    )

                logger.info(
                    f"TOS acceptance already exists for account {account_name} "
                    f"(version: {tos_version}), treating as idempotent success"
                )
            except Exception as e:
                # Roll back the entire transaction including the account update
                session.rollback()

                outcome = "error"

                # METRIC: Track acceptance creation failures (best-effort)
                try:
                    statsd.increment(
                        "tos.acceptance.failed",
                        tags=[f"version:{tos_version}", f"error:{type(e).__name__}"],
                    )
                except Exception as metric_err:
                    logger.warning(
                        f"Failed to emit tos.acceptance.failed metric: {metric_err}"
                    )

                logger.error(
                    f"Failed to record TOS acceptance for account {account_name}: {e}",
                    exc_info=True,
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to record TOS acceptance. Please try again.",
                    headers={"Content-Type": "application/json"},
                ) from e
        else:
            outcome = "duplicate"

            # METRIC: Track duplicate acceptance attempts (best-effort)
            try:
                statsd.increment(
                    "tos.acceptance.duplicate", tags=[f"version:{tos_version}"]
                )
            except Exception as metric_err:
                logger.warning(
                    f"Failed to emit tos.acceptance.duplicate metric: {metric_err}"
                )

            logger.info(
                f"TOS acceptance already exists for account {account_name} "
                f"(version: {tos_version}), returning success"
            )

        # Explicitly commit the transaction (both account update and TOS acceptance)
        try:
            session.commit()
        except Exception as commit_err:
            # Commit failed - rollback and mark as error
            session.rollback()
            outcome = "error"

            # METRIC: Track commit failures (best-effort)
            try:
                statsd.increment(
                    "tos.acceptance.commit_failed",
                    tags=[
                        f"version:{tos_version}",
                        f"error:{type(commit_err).__name__}",
                    ],
                )
            except Exception as metric_err:
                logger.warning(
                    f"Failed to emit tos.acceptance.commit_failed metric: {metric_err}"
                )

            logger.error(
                f"Failed to commit TOS acceptance for account {account_name}: {commit_err}",
                exc_info=True,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save TOS acceptance. Please try again.",
                headers={"Content-Type": "application/json"},
            ) from commit_err

        return AcceptTermsResponse(accepted=True, tos_version=tos_version)

    finally:
        # METRIC: Always track acceptance flow duration with outcome (best-effort)
        try:
            duration_ms = (time.time() - start_time) * 1000
            statsd.histogram(
                "tos.acceptance.duration",
                duration_ms,
                tags=[f"outcome:{outcome}"],
            )
        except Exception as metric_err:
            logger.warning(
                f"Failed to emit tos.acceptance.duration metric: {metric_err}"
            )


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
