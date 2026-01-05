import math
from uuid import UUID

from sqlalchemy.orm import Session

from api.routes.admin import _builder
from api.routes.admin._utils import not_found_error
from api.schemas.admin.history import ChangeLogDetails, ListChangeLogsResponse
from db.tables.change_log import ChangeResourceType
from services import account_service, history_service
from services.auth_types import UserContext


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
    """Authorization handled by require_history_permission in route decorator."""
    change_log = history_service.get_change_log(session, change_log_id)
    if not change_log:
        raise not_found_error(f"Change log does not exist for id: {change_log_id}")

    return _builder.build_change_log_details(change_log)


async def revert_change_log(
    change_log_id: UUID,
    context: UserContext,
    session: Session,
) -> ChangeLogDetails:
    """
    Revert a change log by applying the old values to the resource.
    Authorization handled by require_history_permission in route decorator.
    """
    from fastapi import HTTPException, status

    try:
        revert_log = history_service.revert_change_log(session, change_log_id, context)
        return _builder.build_change_log_details(revert_log)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
