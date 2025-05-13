import uuid

from sqlalchemy.orm import Session

import db
from db import ChangeLog
from db.tables.change_log import ChangeResourceType

from . import _implementation


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


def create_change_log(
    session: Session,
    account_id: uuid.UUID,
    resource_type: ChangeResourceType,
    resource_id: str,
    author: str,
    old_record,
    new_record,
):
    """
    Creates a change log for the given input.

    Args:
        session (Session): database connection
        account_id (uuid.UUID): ID of the account
        resource_type (ChangeResourceType): Name of the edited resource, e.g. Account
        resource_id (str): ID of the edited resource
        author (str): LDAP of the user who performed this edit
        old_record (Base): The db record before the edit
        new_record (Base): The db record after the edit
    """
    return _implementation.create_change_log(
        session, account_id, resource_type, resource_id, author, old_record, new_record
    )


__all__ = [
    "list_account_change_logs",
    "get_change_log",
    "create_change_log",
]
