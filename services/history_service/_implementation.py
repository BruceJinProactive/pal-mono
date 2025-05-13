import uuid

from sqlalchemy import inspect
from sqlalchemy.orm import Session

import db
from db import ChangeLog, ChangeLogRepository
from db.tables.change_log import ChangeAction, ChangeField, ChangeResourceType
from utils.log import logger


def list_account_change_logs(
    session: Session,
    account_id: uuid.UUID,
    page: int,
    page_size: int,
    resource_types: list[ChangeResourceType] | None,
    resource_id: str | None,
) -> tuple[list[ChangeLog], int]:
    change_log_repo = ChangeLogRepository(session)
    skip = (page - 1) * page_size
    change_logs, count = change_log_repo.get_change_logs(
        account_id=account_id,
        skip=skip,
        limit=page_size,
        resource_types=resource_types,
        resource_id=resource_id,
    )
    return change_logs, count


def get_change_log_details(
    session: Session,
    change_log_id: uuid.UUID,
) -> db.ChangeLog | None:
    change_log_repo = ChangeLogRepository(session)
    change_log = change_log_repo.get_change_log(change_log_id)
    return change_log


def create_change_log(
    session: Session,
    account_id: uuid.UUID,
    resource_type: ChangeResourceType,
    resource_id: str,
    author: str,
    old_record,
    new_record,
):
    change_log_repo = ChangeLogRepository(session)
    field_changes = _inspect_field_changes(
        account_id, resource_type, resource_id, old_record, new_record
    )

    if not old_record:
        action = ChangeAction.Create
    elif not new_record:
        action = ChangeAction.Delete
    else:
        action = ChangeAction.Update

    change_log_repo.create_change_log(
        account_id=account_id,
        resource_type=resource_type,
        resource_id=resource_id,
        author=author,
        action=action,
        changes=field_changes,
    )


def _inspect_field_changes(
    account_id: uuid.UUID,
    resource_type: ChangeResourceType,
    resource_id: str,
    old_record,
    new_record,
):
    mapper = None
    if old_record:
        mapper = inspect(type(old_record))
    elif new_record:
        mapper = inspect(type(new_record))
    if not mapper:
        logger.error(
            "Unable to inspect db record",
            extra={
                "account_id": account_id,
                "resource_type": resource_type,
                "resource_id": resource_id,
            },
        )
        return []
    field_changes = []
    for column in mapper.column_attrs:
        column_name = column.key
        if column_name in ["created_at", "updated_at"]:
            # no need to track these timestamps
            continue
        old_value = getattr(old_record, column_name) if old_record else None
        new_value = getattr(new_record, column_name) if new_record else None
        if old_value == new_value:
            continue
        field_changes.append(
            ChangeField(
                field=column_name,
                old_value=str(old_value) if old_value else None,
                new_value=str(new_value) if new_value else None,
            )
        )
    return field_changes
