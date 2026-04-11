from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from db.tables.role_permission import RolePermission
from pal_repository.data_classes.role_permission import RolePermissionData
from utils.log import logger


def _to_data(row: RolePermission) -> RolePermissionData:
    """Convert an ORM RolePermission to a RolePermissionData."""
    return RolePermissionData(
        id=row.id,
        role=row.role,
        permission_id=row.permission_id,
        created_at=row.created_at,
    )


class RolePermissionRepository:
    """Async-only repository for RolePermission records.

    All methods return ``RolePermissionData`` — ORM objects never escape
    this layer.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self, role_permission_id: uuid.UUID
    ) -> RolePermissionData | None:
        """Retrieve a single role-permission mapping by its primary key."""
        try:
            result = await self.session.execute(
                select(RolePermission).filter(RolePermission.id == role_permission_id)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving role permission by ID: {e}")
            raise

    async def list_by_role(self, role: str) -> list[RolePermissionData]:
        """List all permission mappings for a given role."""
        try:
            result = await self.session.execute(
                select(RolePermission).filter(RolePermission.role == role)
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except SQLAlchemyError as e:
            logger.error(f"Error listing role permissions by role: {e}")
            raise

    async def list_by_permission_id(
        self, permission_id: uuid.UUID
    ) -> list[RolePermissionData]:
        """List all role mappings for a given permission."""
        try:
            result = await self.session.execute(
                select(RolePermission).filter(
                    RolePermission.permission_id == permission_id
                )
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except SQLAlchemyError as e:
            logger.error(f"Error listing role permissions by permission ID: {e}")
            raise

    async def get_by_role_and_permission(
        self, role: str, permission_id: uuid.UUID
    ) -> RolePermissionData | None:
        """Retrieve a mapping by both role and permission ID."""
        try:
            result = await self.session.execute(
                select(RolePermission)
                .filter(RolePermission.role == role)
                .filter(RolePermission.permission_id == permission_id)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except SQLAlchemyError as e:
            logger.error(
                f"Error retrieving role permission by role and permission ID: {e}"
            )
            raise

    async def create(self, record: RolePermissionData) -> None:
        """Create a new role-permission mapping.

        Raises:
            Exception: If the insert fails.
        """
        try:
            row = RolePermission(
                id=record.id,
                role=record.role,
                permission_id=record.permission_id,
            )
            self.session.add(row)
            await self.session.commit()
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error creating role permission: {e}")
            raise

    async def delete(self, role_permission_id: uuid.UUID) -> RolePermissionData | None:
        """Delete a role-permission mapping by its ID.

        Returns the deleted record, or None if no match was found.

        Raises:
            Exception: If the delete fails.
        """
        try:
            result = await self.session.execute(
                select(RolePermission).filter(RolePermission.id == role_permission_id)
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
            logger.error(f"Error deleting role permission: {e}")
            raise

    async def delete_by_role_and_permission(
        self, role: str, permission_id: uuid.UUID
    ) -> RolePermissionData | None:
        """Delete a role-permission mapping by role and permission ID.

        Returns the deleted record, or None if no match was found.

        Raises:
            Exception: If the delete fails.
        """
        try:
            result = await self.session.execute(
                select(RolePermission)
                .filter(RolePermission.role == role)
                .filter(RolePermission.permission_id == permission_id)
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
            logger.error(f"Error deleting role permission: {e}")
            raise
