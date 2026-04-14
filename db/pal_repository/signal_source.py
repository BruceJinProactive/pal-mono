from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.signal_source import SignalSourceData
from db.tables.signal_sources import SignalSource
from utils.log import logger


def _to_data(row: SignalSource) -> SignalSourceData:
    """Convert an ORM SignalSource to a SignalSourceData."""
    return SignalSourceData(
        id=row.id,
        account_id=row.account_id,
        project_id=row.project_id,
        signal_type=row.signal_type.value if row.signal_type else "",
        name=row.name,
        description=row.description,
        status=row.status.value if row.status else "",
        status_message=row.status_message,
        config=dict(row.config) if row.config else {},
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SignalSourceRepository:
    """Async-only repository for SignalSource records.

    All methods return ``SignalSourceData`` — ORM objects never escape this layer.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def get_by_id(self, source_id: uuid.UUID) -> SignalSourceData | None:
        """Retrieve a single signal source by its primary key."""
        try:
            result = await self.session.execute(
                select(SignalSource).filter(SignalSource.id == source_id)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            logger.exception("Error retrieving signal source by ID")
            raise

    async def list_by_account(
        self,
        account_id: uuid.UUID,
        signal_type: str | None = None,
    ) -> list[SignalSourceData]:
        """List all signal sources for an account, optionally filtered by type."""
        try:
            stmt = select(SignalSource).filter(SignalSource.account_id == account_id)
            if signal_type is not None:
                stmt = stmt.filter(SignalSource.signal_type == signal_type)
            stmt = stmt.order_by(SignalSource.created_at)
            result = await self.session.execute(stmt)
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception:
            logger.exception("Error listing signal sources by account")
            raise

    async def list_by_project(self, project_id: uuid.UUID) -> list[SignalSourceData]:
        """List all signal sources for a project."""
        try:
            result = await self.session.execute(
                select(SignalSource)
                .filter(SignalSource.project_id == project_id)
                .order_by(SignalSource.created_at)
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception:
            logger.exception("Error listing signal sources by project")
            raise

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def create(self, record: SignalSourceData) -> None:
        """Create a new signal source.

        Raises:
            Exception: If the insert fails.
        """
        try:
            row = SignalSource(
                id=record.id,
                account_id=record.account_id,
                project_id=record.project_id,
                signal_type=record.signal_type,
                name=record.name,
                description=record.description,
                status=record.status,
                status_message=record.status_message,
                config=record.config,
                created_at=record.created_at,
            )
            self.session.add(row)
            await self.session.commit()
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error creating signal source: {e}")
            raise

    async def delete(self, source_id: uuid.UUID) -> SignalSourceData | None:
        """Delete a signal source by its ID.

        Returns the deleted record, or None if no match was found.

        Raises:
            Exception: If the delete fails.
        """
        try:
            result = await self.session.execute(
                select(SignalSource).filter(SignalSource.id == source_id)
            )
            row = result.scalar_one_or_none()
            if not row:
                return None

            data = _to_data(row)
            await self.session.delete(row)
            await self.session.commit()
            return data
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error deleting signal source: {e}")
            raise
