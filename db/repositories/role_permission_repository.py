import uuid

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db.tables import Permission, RolePermission
from utils.log import logger


class RolePermissionRepository:
    """Repository for managing role-permission mappings.

    Maps roles (strings like 'owner', 'manager', 'viewer') to their permissions.
    This defines what each role can do in the system.
    """

    def __init__(self, session: Session, auto_commit: bool = True):
        self.session = session
        self.auto_commit = auto_commit

    def get_permissions_for_role(self, role: str) -> list[Permission]:
        """Get all permission objects for a role.

        Args:
            role: Role string (e.g., 'owner', 'manager', 'viewer')

        Returns:
            List of Permission objects for the role
        """
        try:
            return (
                self.session.query(Permission)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .filter(RolePermission.role == role)
                .order_by(Permission.resource_type, Permission.action)
                .all()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving permissions for role {role}: {e}")
            return []

    def get_permission_names_for_role(self, role: str) -> set[str]:
        """Get permission names for a role (optimized for caching).

        This method is optimized for caching - returns only permission names
        instead of full Permission objects.

        Args:
            role: Role string (e.g., 'owner', 'manager', 'viewer')

        Returns:
            Set of permission name strings (e.g., {'project.create', 'project.read'})
        """
        try:
            results = (
                self.session.query(Permission.name)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .filter(RolePermission.role == role)
                .all()
            )
            return {name for (name,) in results}
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving permission names for role {role}: {e}")
            return set()

    def add_permission_to_role(
        self, role: str, permission_id: uuid.UUID
    ) -> RolePermission:
        """Add a permission to a role.

        If the mapping already exists, returns the existing one.

        Args:
            role: Role string
            permission_id: UUID of the permission

        Returns:
            The created or existing RolePermission object

        Raises:
            SQLAlchemyError: If there's a database error during creation
        """
        try:
            # Check if mapping already exists
            existing = (
                self.session.query(RolePermission)
                .filter(
                    RolePermission.role == role,
                    RolePermission.permission_id == permission_id,
                )
                .first()
            )
            if existing:
                logger.info(
                    f"Role-permission mapping already exists: {role} -> {permission_id}"
                )
                return existing

            # Create new mapping
            db_role_permission = RolePermission(
                id=uuid.uuid4(),
                role=role,
                permission_id=permission_id,
            )
            self.session.add(db_role_permission)

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(db_role_permission)
            logger.info(f"Added permission {permission_id} to role {role}")
            return db_role_permission
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error adding permission to role: {e}")
            raise

    def remove_permission_from_role(self, role: str, permission_id: uuid.UUID) -> bool:
        """Remove a permission from a role.

        Args:
            role: Role string
            permission_id: UUID of the permission

        Returns:
            True if the mapping was deleted, False if not found
        """
        try:
            role_permission = (
                self.session.query(RolePermission)
                .filter(
                    RolePermission.role == role,
                    RolePermission.permission_id == permission_id,
                )
                .first()
            )

            if not role_permission:
                logger.warning(
                    f"Role-permission mapping not found: {role} -> {permission_id}"
                )
                return False

            self.session.delete(role_permission)

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            logger.info(f"Removed permission {permission_id} from role {role}")
            return True
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error removing permission from role: {e}")
            return False

    def get_roles_for_permission(self, permission_id: uuid.UUID) -> list[str]:
        """Get all roles that have a specific permission.

        Args:
            permission_id: UUID of the permission

        Returns:
            List of role strings
        """
        try:
            results = (
                self.session.query(RolePermission.role)
                .filter(RolePermission.permission_id == permission_id)
                .order_by(RolePermission.role)
                .all()
            )
            return [role for (role,) in results]
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving roles for permission: {e}")
            return []

    def bulk_add_permissions_to_role(
        self, role: str, permission_ids: list[uuid.UUID]
    ) -> list[RolePermission]:
        """Batch operation to add multiple permissions to a role.

        Skips permissions that are already mapped to the role.

        Args:
            role: Role string
            permission_ids: List of permission UUIDs

        Returns:
            List of created RolePermission objects (excludes already existing)

        Raises:
            SQLAlchemyError: If there's a database error during creation
        """
        try:
            # Get existing mappings
            results = (
                self.session.query(RolePermission.permission_id)
                .filter(
                    RolePermission.role == role,
                    RolePermission.permission_id.in_(permission_ids),
                )
                .all()
            )
            existing_ids = {pid for (pid,) in results}

            # Deduplicate permission_ids while preserving order
            seen = set()
            unique_permission_ids = []
            for pid in permission_ids:
                if pid not in seen:
                    seen.add(pid)
                    unique_permission_ids.append(pid)

            # Filter out already existing mappings
            new_permission_ids = [
                pid for pid in unique_permission_ids if pid not in existing_ids
            ]

            if not new_permission_ids:
                logger.info(f"All permissions already mapped to role {role}")
                return []

            # Create new mappings
            new_mappings = [
                RolePermission(
                    id=uuid.uuid4(),
                    role=role,
                    permission_id=permission_id,
                )
                for permission_id in new_permission_ids
            ]

            self.session.bulk_save_objects(new_mappings)

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            logger.info(
                f"Bulk added {len(new_mappings)} permissions to role {role} "
                f"(skipped {len(existing_ids)} existing)"
            )
            return new_mappings
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error bulk adding permissions to role: {e}")
            raise
