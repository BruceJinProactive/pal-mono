from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.permission import PermissionData
from db.tables.permission import Permission
from utils.log import logger


def _to_data(row: Permission) -> PermissionData:
    """Convert an ORM Permission to a PermissionData."""
    return PermissionData(
        id=row.id,
        name=row.name,
        resource_type=row.resource_type,
        action=row.action,
        display_name=row.display_name,
        description=row.description,
        created_at=row.created_at,
    )


class PermissionRepository:
    """Async-only repository for Permission records.

    All methods return ``PermissionData`` — ORM objects never escape this layer.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def get_by_id(self, permission_id: uuid.UUID) -> PermissionData | None:
        """Retrieve a single permission by its primary key."""
        try:
            result = await self.session.execute(
                select(Permission).filter(Permission.id == permission_id)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            logger.exception("Error retrieving permission by ID")
            raise

    async def get_by_name(self, name: str) -> PermissionData | None:
        """Retrieve a permission by its unique name (e.g. 'project.create')."""
        try:
            result = await self.session.execute(
                select(Permission).filter(Permission.name == name)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            logger.exception("Error retrieving permission by name")
            raise

    async def list_by_resource_type(self, resource_type: str) -> list[PermissionData]:
        """List all permissions for a given resource type."""
        try:
            result = await self.session.execute(
                select(Permission)
                .filter(Permission.resource_type == resource_type)
                .order_by(Permission.name)
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception:
            logger.exception("Error listing permissions by resource type")
            raise

    async def list_all(self) -> list[PermissionData]:
        """List all permissions, ordered by name."""
        try:
            result = await self.session.execute(
                select(Permission).order_by(Permission.name)
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception:
            logger.exception("Error listing all permissions")
            raise

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def create(self, record: PermissionData) -> None:
        """Create a new permission.

        Raises:
            Exception: If the insert fails.
        """
        try:
            row = Permission(
                id=record.id,
                name=record.name,
                resource_type=record.resource_type,
                action=record.action,
                display_name=record.display_name,
                description=record.description,
            )
            self.session.add(row)
            await self.session.commit()
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error creating permission: {e}")
            raise

    async def delete(self, permission_id: uuid.UUID) -> PermissionData | None:
        """Delete a permission by its ID.

        Returns the deleted record, or None if no match was found.

        Raises:
            Exception: If the delete fails.
        """
        try:
            result = await self.session.execute(
                select(Permission).filter(Permission.id == permission_id)
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
            logger.error(f"Error deleting permission: {e}")
            raise

    async def delete_by_name(self, name: str) -> PermissionData | None:
        """Delete a permission by its unique name.

        Returns the deleted record, or None if no match was found.
        """
        try:
            result = await self.session.execute(
                select(Permission).filter(Permission.name == name)
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
            logger.error(f"Error deleting permission by name: {e}")
            raise
