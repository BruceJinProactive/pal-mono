import ast
import json
import uuid
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm import Session

import db
from db import ChangeLog, ChangeLogRepository
from db.repositories.prompt_repository import PromptRepository
from db.tables.change_log import ChangeAction, ChangeField, ChangeResourceType
from services.auth_types import UserContext
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
    if new_record:
        mapper = inspect(type(new_record))
    elif old_record:
        mapper = inspect(type(old_record))
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


def revert_change_log(
    session: Session,
    change_log_id: uuid.UUID,
    context: UserContext,
) -> db.ChangeLog:
    """
    Revert a change log by applying the old values to the resource.
    Creates a new change log entry for the revert action.

    Args:
        session: Database session
        change_log_id: ID of the change log to revert
        context: User context for authorization and logging

    Returns:
        The new change log entry for the revert action

    Raises:
        ValueError: If the change log is not found or cannot be reverted
    """
    logger.debug(
        f"[history_service._implementation.revert_change_log] Starting revert for change_log_id={change_log_id}"
    )

    change_log_repo = ChangeLogRepository(session)
    change_log = change_log_repo.get_change_log(change_log_id)

    if not change_log:
        logger.debug(
            f"[history_service._implementation.revert_change_log] Change log {change_log_id} not found"
        )
        raise ValueError(
            f"[history_service._implementation.revert_change_log] Change log {change_log_id} not found"
        )

    logger.debug(
        f"[history_service._implementation.revert_change_log] Found change log with resource_type={change_log.resource_type}, "
        f"resource_id={change_log.resource_id}, action={change_log.action}"
    )

    if change_log.action == ChangeAction.Create:
        raise ValueError(
            "[history_service._implementation.revert_change_log] Cannot revert a create action. Please delete the resource instead."
        )

    if change_log.action == ChangeAction.Delete:
        raise ValueError(
            "[history_service._implementation.revert_change_log] Cannot revert a delete action. Please recreate the resource instead."
        )

    resource_type = change_log.resource_type
    resource_id = change_log.resource_id

    old_record = None
    new_record = None

    if resource_type == ChangeResourceType.Account:
        old_record, new_record = _revert_account(
            session, resource_id, change_log.fields
        )
    elif resource_type == ChangeResourceType.Agent:
        old_record, new_record = _revert_agent(session, resource_id, change_log.fields)
    elif resource_type == ChangeResourceType.Project:
        old_record, new_record = _revert_project(
            session, resource_id, change_log.fields
        )
    elif resource_type == ChangeResourceType.Prompt:
        old_record, new_record = _revert_prompt(session, resource_id, change_log.fields)
    else:
        raise ValueError(
            f"[history_service._implementation.revert_change_log] Revert not supported for resource type: {resource_type}"
        )

    field_changes = _inspect_field_changes(
        change_log.account_id, resource_type, resource_id, old_record, new_record
    )

    if not field_changes:
        logger.debug(
            f"[history_service._implementation.revert_change_log] No field changes detected for {resource_type}"
        )
        raise ValueError(
            "[history_service._implementation.revert_change_log] No changes to revert"
        )

    logger.debug(
        f"[history_service._implementation.revert_change_log] Creating revert change log entry with {len(field_changes)} field changes"
    )

    revert_change_log_entry = change_log_repo.create_change_log(
        account_id=change_log.account_id,
        resource_type=resource_type,
        resource_id=resource_id,
        author=context.email,
        action=ChangeAction.Update,
        changes=field_changes,
    )

    if revert_change_log_entry is None:
        raise RuntimeError(
            "[history_service._implementation.revert_change_log] Failed to create revert change log entry"
        )

    session.commit()

    logger.debug(
        f"[history_service._implementation.revert_change_log] Successfully reverted change_log_id={change_log_id}, "
        f"new_change_log_id={revert_change_log_entry.id}"
    )

    return revert_change_log_entry


def _revert_account(
    session: Session,
    resource_id: str,
    fields: list[ChangeField],
) -> tuple[Any, db.Account]:
    """Revert account changes by applying old values.

    Uses repository directly to avoid automatic change log creation from service layer.
    """
    logger.debug(
        f"[history_service._implementation._revert_account] Reverting account {resource_id}"
    )

    account_repository = db.AccountRepository(session, auto_commit=False)
    account = account_repository.get_account_by_id(uuid.UUID(resource_id))
    if not account:
        raise ValueError(
            f"[history_service._implementation._revert_account] Account {resource_id} not found"
        )

    old_record = _copy_record(account)
    update_params = _build_update_params(fields)

    logger.debug(
        f"[history_service._implementation._revert_account] Applying {len(update_params)} field updates to account {account.name}"
    )

    if update_params:
        updated_account = account_repository.update_account(
            account.name, expected_version=None, **update_params
        )
        if updated_account:
            account = updated_account

    logger.debug(
        f"[history_service._implementation._revert_account] Successfully reverted account {resource_id}"
    )
    return old_record, account


def _revert_agent(
    session: Session,
    resource_id: str,
    fields: list[ChangeField],
) -> tuple[Any, db.Agent]:
    """Revert agent changes by applying old values.

    Uses repository directly to avoid automatic change log creation from service layer.
    """
    logger.debug(
        f"[history_service._implementation._revert_agent] Reverting agent {resource_id}"
    )

    agent_repository = db.AgentRepository(session, auto_commit=False)
    agent = agent_repository.get_agent(uuid.UUID(resource_id))
    if not agent:
        raise ValueError(
            f"[history_service._implementation._revert_agent] Agent {resource_id} not found"
        )

    old_record = _copy_record(agent)
    update_params = _build_update_params(fields)

    logger.debug(
        f"[history_service._implementation._revert_agent] Applying {len(update_params)} field updates to agent {resource_id}"
    )

    if update_params:
        updated_agent = agent_repository.update_agent(
            uuid.UUID(resource_id), expected_version=None, **update_params
        )
        if updated_agent:
            agent = updated_agent

    logger.debug(
        f"[history_service._implementation._revert_agent] Successfully reverted agent {resource_id}"
    )
    return old_record, agent


def _revert_project(
    session: Session,
    resource_id: str,
    fields: list[ChangeField],
) -> tuple[Any, db.Project]:
    """Revert project changes by applying old values.

    Uses repository directly to avoid automatic change log creation from service layer.
    """
    logger.debug(
        f"[history_service._implementation._revert_project] Reverting project {resource_id}"
    )

    project_repository = db.ProjectRepository(session, auto_commit=False)
    project = project_repository.get_project(uuid.UUID(resource_id))
    if not project:
        raise ValueError(
            f"[history_service._implementation._revert_project] Project {resource_id} not found"
        )

    old_record = _copy_record(project)
    update_params = _build_update_params(fields)

    logger.debug(
        f"[history_service._implementation._revert_project] Applying {len(update_params)} field updates to project {resource_id}"
    )

    if update_params:
        updated_project = project_repository.update_project(
            uuid.UUID(resource_id), expected_version=None, **update_params
        )
        if updated_project:
            project = updated_project

    logger.debug(
        f"[history_service._implementation._revert_project] Successfully reverted project {resource_id}"
    )
    return old_record, project


def _revert_prompt(
    session: Session,
    resource_id: str,
    fields: list[ChangeField],
) -> tuple[Any, db.Prompt]:
    """Revert prompt changes by applying old values."""
    logger.debug(
        f"[history_service._implementation._revert_prompt] Reverting prompt {resource_id}"
    )

    prompt_repository = PromptRepository(session, auto_commit=False)
    prompt = prompt_repository.get_prompt_by_id(uuid.UUID(resource_id))
    if not prompt:
        raise ValueError(
            f"[history_service._implementation._revert_prompt] Prompt {resource_id} not found"
        )

    old_record = _copy_record(prompt)
    update_params = _build_update_params(fields)

    logger.debug(
        f"[history_service._implementation._revert_prompt] Applying {len(update_params)} field updates to prompt {resource_id}"
    )

    if update_params:
        updated_prompt = prompt_repository.update_prompt(
            uuid.UUID(resource_id), **update_params
        )
        if updated_prompt:
            prompt = updated_prompt

    logger.debug(
        f"[history_service._implementation._revert_prompt] Successfully reverted prompt {resource_id}"
    )
    return old_record, prompt


def _build_update_params(fields: list[ChangeField]) -> dict[str, Any]:
    """Build update params dict from change log fields by parsing old values."""
    update_params: dict[str, Any] = {}
    for field in fields:
        if field.old_value is not None:
            update_params[field.field] = _parse_field_value(
                field.field, field.old_value
            )
    return update_params


def _copy_record(record):
    """Create a shallow copy of a record for comparison."""

    class RecordCopy:
        pass

    copy = RecordCopy()
    mapper = inspect(type(record))
    for column in mapper.column_attrs:
        setattr(copy, column.key, getattr(record, column.key))
    return copy


def _parse_field_value(field_name: str, value: str):
    """Parse a field value from string to the appropriate type."""
    if value == "None" or value == "null":
        return None

    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False

    try:
        return int(value)
    except ValueError:
        pass

    try:
        return float(value)
    except ValueError:
        pass

    if value.startswith("{") or value.startswith("["):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass
        try:
            parsed = ast.literal_eval(value)
            if isinstance(parsed, (dict, list)):
                return parsed
        except (ValueError, SyntaxError):
            pass

    try:
        return uuid.UUID(value)
    except ValueError:
        pass

    return value
