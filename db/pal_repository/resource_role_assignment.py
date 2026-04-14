from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.resource_role_assignment import (
    ResourceRoleAssignmentData,
)
from db.tables.resource_role_assignment import ResourceRoleAssignment
from utils.log import logger


def _to_data(row: ResourceRoleAssignment) -> ResourceRoleAssignmentData:
    """Convert an ORM ResourceRoleAssignment to a ResourceRoleAssignmentData."""
    return ResourceRoleAssignmentData(
        id=row.id,
        user_id=row.user_id,
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        role=row.role,
        assigned_by=row.assigned_by,
        assigned_at=row.assigned_at,
        reason=row.reason,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class ResourceRoleAssignmentRepository:
    """Async-only repository for ResourceRoleAssignment records.

    All methods return ``ResourceRoleAssignmentData`` — ORM objects never
    escape this layer.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def get_by_id(
        self, assignment_id: uuid.UUID
    ) -> ResourceRoleAssignmentData | None:
        """Retrieve a single assignment by its primary key."""
        try:
            result = await self.session.execute(
                select(ResourceRoleAssignment).filter(
                    ResourceRoleAssignment.id == assignment_id
                )
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            logger.exception("Error retrieving resource role assignment by ID")
            raise

    async def list_by_user(
        self,
        user_id: uuid.UUID,
        resource_type: str | None = None,
    ) -> list[ResourceRoleAssignmentData]:
        """List all assignments for a user, optionally filtered by resource type."""
        try:
            stmt = select(ResourceRoleAssignment).filter(
                ResourceRoleAssignment.user_id == user_id
            )
            if resource_type is not None:
                stmt = stmt.filter(
                    ResourceRoleAssignment.resource_type == resource_type
                )
            stmt = stmt.order_by(ResourceRoleAssignment.created_at)
            result = await self.session.execute(stmt)
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception:
            logger.exception("Error listing assignments by user")
            raise

    async def list_by_resource(
        self,
        resource_type: str,
        resource_id: uuid.UUID,
    ) -> list[ResourceRoleAssignmentData]:
        """List all assignments for a specific resource."""
        try:
            result = await self.session.execute(
                select(ResourceRoleAssignment)
                .filter(
                    ResourceRoleAssignment.resource_type == resource_type,
                    ResourceRoleAssignment.resource_id == resource_id,
                )
                .order_by(ResourceRoleAssignment.created_at)
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception:
            logger.exception("Error listing assignments by resource")
            raise

    async def get_roles_for_resource(
        self,
        user_id: uuid.UUID,
        resource_type: str,
        resource_id: uuid.UUID,
    ) -> list[str]:
        """Return the role strings a user holds on a specific resource."""
        try:
            result = await self.session.execute(
                select(ResourceRoleAssignment.role).filter(
                    ResourceRoleAssignment.user_id == user_id,
                    ResourceRoleAssignment.resource_type == resource_type,
                    ResourceRoleAssignment.resource_id == resource_id,
                )
            )
            return list(result.scalars().all())
        except Exception:
            logger.exception("Error getting roles for resource")
            raise

    async def has_role(
        self,
        user_id: uuid.UUID,
        resource_type: str,
        resource_id: uuid.UUID,
        role: str,
    ) -> bool:
        """Check whether a user holds a specific role on a resource."""
        try:
            result = await self.session.execute(
                select(ResourceRoleAssignment.id).filter(
                    ResourceRoleAssignment.user_id == user_id,
                    ResourceRoleAssignment.resource_type == resource_type,
                    ResourceRoleAssignment.resource_id == resource_id,
                    ResourceRoleAssignment.role == role,
                )
            )
            return result.scalar_one_or_none() is not None
        except Exception:
            logger.exception("Error checking role")
            raise

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def create(self, record: ResourceRoleAssignmentData) -> None:
        """Create a new role assignment.

        Raises:
            Exception: If the insert fails.
        """
        try:
            row = ResourceRoleAssignment(
                id=record.id,
                user_id=record.user_id,
                resource_type=record.resource_type,
                resource_id=record.resource_id,
                role=record.role,
                assigned_by=record.assigned_by,
                assigned_at=record.assigned_at,
                reason=record.reason,
                created_at=record.created_at,
            )
            self.session.add(row)
            await self.session.commit()
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error creating resource role assignment: {e}")
            raise

    async def delete(
        self, assignment_id: uuid.UUID
    ) -> ResourceRoleAssignmentData | None:
        """Delete an assignment by its ID.

        Returns the deleted record, or None if no match was found.

        Raises:
            Exception: If the delete fails.
        """
        try:
            result = await self.session.execute(
                select(ResourceRoleAssignment).filter(
                    ResourceRoleAssignment.id == assignment_id
                )
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
            logger.error(f"Error deleting resource role assignment: {e}")
            raise

    async def delete_by_user_and_resource(
        self,
        user_id: uuid.UUID,
        resource_type: str,
        resource_id: uuid.UUID,
        role: str,
    ) -> ResourceRoleAssignmentData | None:
        """Delete a specific role assignment for a user on a resource.

        Returns the deleted record, or None if no match was found.
        """
        try:
            result = await self.session.execute(
                select(ResourceRoleAssignment).filter(
                    ResourceRoleAssignment.user_id == user_id,
                    ResourceRoleAssignment.resource_type == resource_type,
                    ResourceRoleAssignment.resource_id == resource_id,
                    ResourceRoleAssignment.role == role,
                )
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
            logger.error(f"Error deleting assignment by user and resource: {e}")
            raise
