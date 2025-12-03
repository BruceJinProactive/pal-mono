import math
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from api.routes.admin import _builder
from api.routes.admin._utils import not_found_error
from api.schemas.admin.history import ChangeLogDetails, ListChangeLogsResponse
from db.tables.change_log import ChangeResourceType
from services import account_service, history_service
from services.auth_service import check_permission, is_rbac_enabled
from services.auth_types import UserContext, UserRole
from utils.log import logger


async def list_account_change_logs(
    context: UserContext,
    session: Session,
    account_name: str,
    page: int,
    page_size: int,
    resource_types: list[ChangeResourceType] | None,
    resource_id: str | None,
) -> ListChangeLogsResponse:
    """Authorization is handled by require_account_permission in route decorator."""
    account = account_service.get_account(session, account_name)
    if not account:
        raise not_found_error(f"Account {account_name} not found.")

    change_logs, total = history_service.list_account_change_logs(
        session,
        account.id,
        page,
        page_size,
        resource_types,
        resource_id,
    )
    total_pages = math.ceil(total / page_size)
    return ListChangeLogsResponse(
        changes=[
            _builder.build_change_log_summary(change_log) for change_log in change_logs
        ],
        total_changes=total,
        total_pages=int(total_pages),
    )


async def get_change_log_details(
    change_log_id: UUID,
    context: UserContext,
    session: Session,
) -> ChangeLogDetails:
    change_log = history_service.get_change_log(session, change_log_id)
    if not change_log:
        raise not_found_error(f"Change log does not exist for id: {change_log_id}")

    account = account_service.get_account_by_id(session, change_log.account_id)
    if account:
        # RBAC check using account resource
        if not is_rbac_enabled():
            # Legacy: check account membership
            if account.name not in context.account_names:
                if context.role != UserRole.Admin:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="User does not have permission for the requested account",
                        headers={"Content-Type": "application/json"},
                    )
        else:
            # RBAC: Admin has full access
            if context.role == UserRole.Admin:
                return _builder.build_change_log_details(change_log)
            # RBAC: check permission on account
            user_id = UUID(context.username)
            if not check_permission(
                user_id, f"accounts/{account.id}", "account.read", session
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Missing required permission: account.read",
                    headers={"Content-Type": "application/json"},
                )
    else:
        logger.error("Account does not exist for the change log.")

    return _builder.build_change_log_details(change_log)
