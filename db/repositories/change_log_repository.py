import uuid
from typing import List, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db.tables import ChangeAction, ChangeField, ChangeLog
from db.tables.change_log import ChangeResourceType
from utils.log import logger


class ChangeLogRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_change_logs(
        self,
        account_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
        resource_types: list[ChangeResourceType] | None = None,
        resource_id: str | None = None,
    ) -> tuple[List[ChangeLog], int]:
        """Retrieve a list of change changes for a given account with optional filtering."""
        try:
            query = self.session.query(ChangeLog).filter(
                ChangeLog.account_id == account_id
            )

            if resource_types:
                query = query.filter(ChangeLog.resource_type.in_(resource_types))
            if resource_id:
                query = query.filter(ChangeLog.resource_id == resource_id)

            total = query.count()
            change_logs = (
                query.order_by(ChangeLog.created_at.desc())
                .offset(skip)
                .limit(limit)
                .all()
            )
            return change_logs, total
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving change logs: {e}")
            return [], 0

    def get_change_log(self, change_log_id: uuid.UUID) -> ChangeLog | None:
        """Retrieve a specific change log by its ID."""
        try:
            return (
                self.session.query(ChangeLog)
                .filter(ChangeLog.id == change_log_id)
                .first()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving change log: {e}")
            return None

    def create_change_log(
        self,
        account_id: uuid.UUID,
        resource_type: ChangeResourceType,
        resource_id: str,
        author: str,
        action: ChangeAction,
        changes: List[ChangeField],
    ) -> Optional[ChangeLog]:
        """
        Create a new change log with associated changes.

        Args:
            account_id: The ID of the account
            resource_type: The type of resource being changed (e.g., 'account', 'project')
            resource_id: The ID of the resource being changed
            author: The username or identifier of who made the changes
            action: The type of action performed (edit, add, delete)
            changes: List of dictionaries containing field, old_value, and new_value

        Note:
            Empty changes list is valid - indicates an action occurred without metadata changes.
            For example, prompt content updates create new PromptDetails versions but don't
            change the Prompt metadata, resulting in empty changes while still being tracked.
        """
        try:
            # Create the change log
            change_log = ChangeLog(
                account_id=account_id,
                resource_type=resource_type,
                resource_id=resource_id,
                author=author,
                action=action,
            )
            self.session.add(change_log)
            self.session.flush()
            self.session.refresh(change_log)

            # Create the changed fields
            for change in changes:
                change.change_log = change_log
                self.session.add(change)

            return change_log
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error creating change log: {e}")
            return None
