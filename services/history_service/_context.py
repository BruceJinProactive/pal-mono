from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from db.tables.change_log import ChangeResourceType
from services.history_service._implementation import create_change_log
from utils.log import logger


class ChangeLogContext:
    def __init__(
        self,
        session: Session,
        resource_type: ChangeResourceType,
        author: str,
        account_id: Optional[UUID] = None,
        resource_id: Optional[str] = None,
        old_record: Optional[Any] = None,
        new_record: Optional[Any] = None,
        auto_commit: bool = True,
    ):
        self._session = session
        self._account_id = account_id or UUID(int=0)
        self._resource_type = resource_type
        self._resource_id = resource_id
        self._author = author
        self._old_record = old_record
        self._new_record = new_record
        self._auto_commit = auto_commit

    @property
    def account_id(self) -> Optional[UUID]:
        return self._account_id

    @account_id.setter
    def account_id(self, value: UUID):
        self._account_id = value

    @property
    def resource_id(self) -> Optional[str]:
        return self._resource_id

    @resource_id.setter
    def resource_id(self, value: str):
        self._resource_id = value

    @property
    def old_record(self) -> Optional[Any]:
        return self._old_record

    @old_record.setter
    def old_record(self, value: Optional[Any]):
        self._old_record = value

    @property
    def new_record(self) -> Optional[Any]:
        return self._new_record

    @new_record.setter
    def new_record(self, value: Optional[Any]):
        self._new_record = value

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self._session.rollback()
            logger.error(f"Operation failed due to error: {exc_val}")
            return False  # Re-raise the exception

        try:
            if self._resource_id is None:
                logger.warning("Skipping change log creation: resource_id is not set")
                return True

            create_change_log(
                session=self._session,
                account_id=self._account_id,
                resource_type=self._resource_type,
                resource_id=self._resource_id,
                author=self._author,
                old_record=self._old_record,
                new_record=self._new_record,
            )

            if self._auto_commit:
                self._session.commit()
            else:
                self._session.flush()
            return True
        except Exception as e:
            self._session.rollback()
            logger.error(f"Failed to create change log due to error: {e}")
            raise
