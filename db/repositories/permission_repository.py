import uuid
from typing import Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db.tables import Permission
from utils.log import logger


class PermissionRepository:
    """Repository for managing permissions.

    Permissions define what actions can be performed on resources.
    Format: 'resource.action' (e.g., 'project.create', 'account.read')
    """

    def __init__(self, session: Session, auto_commit: bool = True):
        self.session = session
        self.auto_commit = auto_commit

    def get_by_name(self, name: str) -> Optional[Permission]:
        """Retrieve a permission by its name.

        Args:
            name: Permission name in format 'resource.action'

        Returns:
            Permission object or None if not found
        """
        try:
            return (
                self.session.query(Permission).filter(Permission.name == name).first()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving permission by name: {e}")
            return None

    def get_by_id(self, permission_id: uuid.UUID) -> Optional[Permission]:
        """Retrieve a permission by its ID.

        Args:
            permission_id: UUID of the permission

        Returns:
            Permission object or None if not found
        """
        try:
            return (
                self.session.query(Permission)
                .filter(Permission.id == permission_id)
                .first()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving permission by ID: {e}")
            return None

    def get_all(self) -> list[Permission]:
        """Retrieve all permissions.

        Returns:
            List of all permissions, ordered by resource_type and action
        """
        try:
            return (
                self.session.query(Permission)
                .order_by(Permission.resource_type, Permission.action)
                .all()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving all permissions: {e}")
            return []

    def get_by_resource_type(self, resource_type: str) -> list[Permission]:
        """Retrieve all permissions for a specific resource type.

        Args:
            resource_type: Resource type (e.g., 'project', 'account', 'agent')

        Returns:
            List of permissions for the resource type, ordered by action
        """
        try:
            return (
                self.session.query(Permission)
                .filter(Permission.resource_type == resource_type)
                .order_by(Permission.action)
                .all()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving permissions by resource type: {e}")
            return []

    def create(
        self,
        name: str,
        resource_type: str,
        action: str,
        display_name: str,
        description: Optional[str] = None,
    ) -> Permission:
        """Create a new permission.

        If a permission with the same name already exists, returns the existing one.

        Args:
            name: Permission name in format 'resource.action'
            resource_type: Resource type (e.g., 'project', 'account')
            action: Action (e.g., 'create', 'read', 'write', 'delete')
            display_name: Human-readable name
            description: Optional description

        Returns:
            The created or existing Permission object

        Raises:
            SQLAlchemyError: If there's a database error during creation
        """
        try:
            # Check if permission already exists
            existing = self.get_by_name(name)
            if existing:
                logger.info(f"Permission {name} already exists, returning existing")
                return existing

            # Create new permission
            db_permission = Permission(
                id=uuid.uuid4(),
                name=name,
                resource_type=resource_type,
                action=action,
                display_name=display_name,
                description=description,
            )
            self.session.add(db_permission)

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(db_permission)
            logger.info(f"Created permission: {name}")
            return db_permission
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error creating permission: {e}")
            raise
