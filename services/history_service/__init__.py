import uuid
from contextlib import contextmanager
from typing import Any, Optional

from sqlalchemy.orm import Session

import db
from db import ChangeLog
from db.tables.change_log import ChangeResourceType

from . import _implementation
from ._context import ChangeLogContext


def list_account_change_logs(
    session: Session,
    account_id: uuid.UUID,
    page: int,
    page_size: int,
    resource_types: list[ChangeResourceType] | None,
    resource_id: str | None,
) -> tuple[list[ChangeLog], int]:
    """
    Returns a list of change logs for an account with optional filters.

    Args:
        session (Session): database connection
        account_id (uuid.UUID): ID of the account to retrieve change logs for
        page (int): Current page number (starts at 1)
        page_size (int): Number of change logs to retrieve
        resource_types (list[ChangeResourceType]): List of the resource types, e.g. "Account", "Agent", etc...
        resource_id (str): Database ID of that resource (usually a UUID)

    Returns:
        tuple[list[ChangeLog], int]: Paginated list of paginated change logs for the account
         and the total number of change logs for the account
    """
    return _implementation.list_account_change_logs(
        session, account_id, page, page_size, resource_types, resource_id
    )


def get_change_log(
    session: Session,
    change_log_id: uuid.UUID,
) -> db.ChangeLog | None:
    """
    Retrieve the details of the specified change log

    Args:
        session (Session): database connection
        change_log_id (uuid.UUID): ID of the change log

    Returns:
        db.ChangeLog: Detailed change log with changed fields or None.
    """
    return _implementation.get_change_log_details(session, change_log_id)


@contextmanager
def change_log_context(
    session: Session,
    resource_type: ChangeResourceType,
    author: str,
    account_id: Optional[uuid.UUID] = None,
    resource_id: Optional[str] = None,
    old_record: Optional[Any] = None,
    new_record: Optional[Any] = None,
    auto_commit: bool = True,
):
    """
    A context manager for creating change logs with built-in exception handling and session management.
    Usage example:

    with change_log_context(
        session=session,
        resource_type=ChangeResourceType.Account,
        author=context.email,
        old_record=old_account,
        new_record=new_account,
        auto_commit=True,  # Set to False if you want to manage commits yourself
    ) as ctx:
        # Perform the operation that needs to be logged
        account = account_repository.create_account(...)
        # Update context with actual values if needed
        ctx.account_id = account.id
        ctx.resource_id = str(account.id)
        ctx.new_record = account
    """
    context = ChangeLogContext(
        session=session,
        resource_type=resource_type,
        author=author,
        account_id=account_id,
        resource_id=resource_id,
        old_record=old_record,
        new_record=new_record,
        auto_commit=auto_commit,
    )
    with context as ctx:
        yield ctx


__all__ = [
    "list_account_change_logs",
    "get_change_log",
    "change_log_context",
]
