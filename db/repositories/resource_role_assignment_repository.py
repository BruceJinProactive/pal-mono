import uuid
from collections.abc import Collection
from enum import Enum
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from db.tables import AccountUser, ResourceRoleAssignment
from db.tables.types import AccountUserStatus
from utils.log import logger


class ResourceType(str, Enum):
    """Resource types for RBAC system.

    Values are singular forms used in the database.
    API layer uses plural forms which can be converted via from_plural().
    """

    ACCOUNT = "account"
    PROJECT = "project"
    AGENT = "agent"
    CHECKLIST = "checklist"
    PLAN = "plan"
    DATA = "data"
    HISTORY = "history"
    FEEDBACK = "feedback"
    CAMPAIGN = "campaign"
    KNOWLEDGE = "knowledge"
    SUBSCRIPTION = "subscription"
    ROUTINE = "routine"
    EXECUTION = "execution"
    SUBMISSION = "submission"

    @classmethod
    def from_plural(cls, plural: str) -> "ResourceType":
        """Convert plural form (from API) to ResourceType enum.

        Args:
            plural: Plural form (e.g., 'accounts', 'projects')

        Returns:
            ResourceType enum

        Raises:
            ValueError: If plural form is not recognized
        """
        mapping = {
            "accounts": cls.ACCOUNT,
            "projects": cls.PROJECT,
            "agents": cls.AGENT,
            "checklists": cls.CHECKLIST,
            "plans": cls.PLAN,
            "data": cls.DATA,
            "histories": cls.HISTORY,
            "feedbacks": cls.FEEDBACK,
            "campaigns": cls.CAMPAIGN,
            "knowledges": cls.KNOWLEDGE,
            "subscriptions": cls.SUBSCRIPTION,
            "routines": cls.ROUTINE,
            "executions": cls.EXECUTION,
            "submissions": cls.SUBMISSION,
        }
        if plural not in mapping:
            raise ValueError(f"Unknown resource type: {plural}")
        return mapping[plural]

    def to_plural(self) -> str:
        """Convert to plural form (for API).

        Returns:
            Plural form string (e.g., 'accounts', 'projects')
        """
        mapping = {
            self.ACCOUNT: "accounts",
            self.PROJECT: "projects",
            self.AGENT: "agents",
            self.CHECKLIST: "checklists",
            self.PLAN: "plans",
            self.DATA: "data",
            self.HISTORY: "histories",
            self.FEEDBACK: "feedbacks",
            self.CAMPAIGN: "campaigns",
            self.KNOWLEDGE: "knowledges",
            self.SUBSCRIPTION: "subscriptions",
            self.ROUTINE: "routines",
            self.EXECUTION: "executions",
            self.SUBMISSION: "submissions",
        }
        return mapping[self]


class ResourceRoleAssignmentRepository:
    """Repository for managing role assignments on resources.

    Unified repository for ALL role assignments on ANY resource:
    - Account-level: resource_type='account', resource_id=account_id
    - Project-level: resource_type='project', resource_id=project_id
    - Agent-level: resource_type='agent', resource_id=agent_id
    - Any future resource types

    Design principle: Users can have MULTIPLE roles on the same resource.
    Example: User can be both 'owner' AND 'billing_admin' on an account.
    """

    def __init__(self, session: Session, auto_commit: bool = True):
        self.session = session
        self.auto_commit = auto_commit

    @staticmethod
    def _normalize_resource_type(resource_type: ResourceType) -> str:
        """Normalize resource_type to string value.

        Args:
            resource_type: ResourceType enum

        Returns:
            String value of the resource type
        """
        return resource_type.value

    def get_roles_for_resource(
        self, user_id: uuid.UUID, resource_type: ResourceType, resource_id: uuid.UUID
    ) -> list[str]:
        """Get all roles a user has on a specific resource.

        This is the CORE permission check query - returns all roles the user
        has on a specific resource instance.

        Args:
            user_id: UUID of the user
            resource_type: ResourceType enum (e.g., ResourceType.ACCOUNT)
            resource_id: UUID of the specific resource

        Returns:
            List of role strings (e.g., ['owner', 'billing_admin']) or empty list
        """
        resource_type_str = self._normalize_resource_type(resource_type)
        try:
            assignments = (
                self.session.query(ResourceRoleAssignment)
                .filter(
                    ResourceRoleAssignment.user_id == user_id,
                    ResourceRoleAssignment.resource_type == resource_type_str,
                    ResourceRoleAssignment.resource_id == resource_id,
                )
                .all()
            )
            return [assignment.role for assignment in assignments]
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving roles for resource: {e}")
            return []

    def has_role(
        self,
        user_id: uuid.UUID,
        resource_type: ResourceType,
        resource_id: uuid.UUID,
        role: str,
    ) -> bool:
        """Check if user has a specific role on a resource.

        Convenience method for permission checks.

        Args:
            user_id: UUID of the user
            resource_type: Resource type
            resource_id: UUID of the resource
            role: Role to check for

        Returns:
            True if user has the role, False otherwise
        """
        roles = self.get_roles_for_resource(user_id, resource_type, resource_id)
        return role in roles

    def has_any_role(
        self,
        user_id: uuid.UUID,
        resource_type: ResourceType,
        resource_id: uuid.UUID,
        roles: frozenset[str],
    ) -> bool:
        """Check if user has any role from a set on a resource."""
        user_roles = self.get_roles_for_resource(user_id, resource_type, resource_id)
        return any(role in roles for role in user_roles)

    def get_assignments_for_user(
        self, user_id: uuid.UUID, resource_type: Optional[ResourceType] = None
    ) -> list[ResourceRoleAssignment]:
        """Get all role assignments for a user.

        Args:
            user_id: UUID of the user
            resource_type: Optional ResourceType enum filter

        Returns:
            List of ResourceRoleAssignment objects, ordered by created_at desc
        """
        try:
            query = self.session.query(ResourceRoleAssignment).filter(
                ResourceRoleAssignment.user_id == user_id
            )

            if resource_type:
                resource_type_str = self._normalize_resource_type(resource_type)
                query = query.filter(
                    ResourceRoleAssignment.resource_type == resource_type_str
                )

            return query.order_by(ResourceRoleAssignment.created_at.desc()).all()
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving assignments for user: {e}")
            return []

    def get_assignments_for_resource(
        self, resource_type: ResourceType, resource_id: uuid.UUID
    ) -> list[ResourceRoleAssignment]:
        """Get all role assignments for a specific resource.

        Used for listing team members who have access to a resource.

        Args:
            resource_type: ResourceType enum (e.g., ResourceType.ACCOUNT)
            resource_id: UUID of the resource

        Returns:
            List of ResourceRoleAssignment objects, ordered by role alphabetically, then created_at
        """
        resource_type_str = self._normalize_resource_type(resource_type)
        try:
            return (
                self.session.query(ResourceRoleAssignment)
                .filter(
                    ResourceRoleAssignment.resource_type == resource_type_str,
                    ResourceRoleAssignment.resource_id == resource_id,
                )
                .order_by(
                    ResourceRoleAssignment.role, ResourceRoleAssignment.created_at
                )
                .all()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving assignments for resource: {e}")
            return []

    def get_assignments_for_resources(
        self, resource_type: ResourceType, resource_ids: list[uuid.UUID]
    ) -> list[ResourceRoleAssignment]:
        """Get all role assignments for multiple resources in a single query.

        Used for batch lookups to avoid O(n) queries when processing multiple resources.

        Args:
            resource_type: ResourceType enum (e.g., ResourceType.PROJECT)
            resource_ids: List of resource UUIDs to fetch assignments for

        Returns:
            List of ResourceRoleAssignment objects for all specified resources
        """
        if not resource_ids:
            return []

        resource_type_str = self._normalize_resource_type(resource_type)
        try:
            return (
                self.session.query(ResourceRoleAssignment)
                .filter(
                    ResourceRoleAssignment.resource_type == resource_type_str,
                    ResourceRoleAssignment.resource_id.in_(resource_ids),
                )
                .all()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving assignments for resources: {e}")
            return []

    def add_role(
        self,
        user_id: uuid.UUID,
        resource_type: ResourceType,
        resource_id: uuid.UUID,
        role: str,
        assigned_by: Optional[uuid.UUID] = None,
        reason: Optional[str] = None,
    ) -> ResourceRoleAssignment:
        """Add a role to a user on a resource.

        Idempotent operation - if the role assignment already exists, returns the existing one.

        Args:
            user_id: UUID of the user
            resource_type: ResourceType enum (e.g., ResourceType.ACCOUNT)
            resource_id: UUID of the resource
            role: Role string (e.g., 'owner', 'manager', 'viewer', 'billing_admin')
            assigned_by: Optional UUID of user who made this assignment
            reason: Optional reason for assignment

        Returns:
            The created or existing ResourceRoleAssignment object

        Raises:
            SQLAlchemyError: If there's a database error during operation
        """
        resource_type_str = self._normalize_resource_type(resource_type)
        try:
            # Check if this exact role assignment already exists
            existing = (
                self.session.query(ResourceRoleAssignment)
                .filter(
                    ResourceRoleAssignment.user_id == user_id,
                    ResourceRoleAssignment.resource_type == resource_type_str,
                    ResourceRoleAssignment.resource_id == resource_id,
                    ResourceRoleAssignment.role == role,
                )
                .first()
            )

            if existing:
                logger.info(
                    f"Role assignment already exists: user {user_id} has role {role} on {resource_type_str}:{resource_id}"
                )
                return existing

            # Create new assignment
            db_assignment = ResourceRoleAssignment(
                id=uuid.uuid4(),
                user_id=user_id,
                resource_type=resource_type_str,
                resource_id=resource_id,
                role=role,
                assigned_by=assigned_by,
                reason=reason,
            )
            self.session.add(db_assignment)

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(db_assignment)
            logger.info(
                f"Added role: user {user_id} as {role} on {resource_type_str}:{resource_id}"
            )
            return db_assignment
        except IntegrityError:
            # Concurrent insert - fetch the existing assignment
            self.session.rollback()
            existing = (
                self.session.query(ResourceRoleAssignment)
                .filter(
                    ResourceRoleAssignment.user_id == user_id,
                    ResourceRoleAssignment.resource_type == resource_type_str,
                    ResourceRoleAssignment.resource_id == resource_id,
                    ResourceRoleAssignment.role == role,
                )
                .first()
            )
            if existing:
                logger.info(
                    f"Role assignment created concurrently: user {user_id} has role {role} on {resource_type_str}:{resource_id}"
                )
                return existing
            # If still not found, re-raise original error
            raise
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error adding role: {e}")
            raise

    def add_roles_bulk(
        self,
        user_id: uuid.UUID,
        resource_type: ResourceType,
        resource_ids: list[uuid.UUID],
        role: str,
        assigned_by: Optional[uuid.UUID] = None,
        reason: Optional[str] = None,
    ) -> list[ResourceRoleAssignment]:
        """Add the same role to a user on multiple resources atomically.

        This is more efficient than calling add_role() in a loop as it:
        1. Checks for existing assignments in a single query
        2. Inserts all new assignments in a single batch

        Idempotent - existing assignments are returned without modification.

        Args:
            user_id: UUID of the user
            resource_type: ResourceType enum (e.g., ResourceType.PROJECT)
            resource_ids: List of resource UUIDs to assign the role on
            role: Role string (e.g., 'staff', 'manager')
            assigned_by: Optional UUID of user who made this assignment
            reason: Optional reason for assignment

        Returns:
            List of all ResourceRoleAssignment objects (existing + newly created)

        Raises:
            SQLAlchemyError: If there's a database error during operation
        """
        if not resource_ids:
            return []

        # Deduplicate resource_ids while preserving order
        seen: set[UUID] = set()
        unique_resource_ids: list[UUID] = []
        for rid in resource_ids:
            if rid not in seen:
                seen.add(rid)
                unique_resource_ids.append(rid)

        resource_type_str = self._normalize_resource_type(resource_type)
        try:
            # Find existing assignments in one query
            existing = (
                self.session.query(ResourceRoleAssignment)
                .filter(
                    ResourceRoleAssignment.user_id == user_id,
                    ResourceRoleAssignment.resource_type == resource_type_str,
                    ResourceRoleAssignment.resource_id.in_(unique_resource_ids),
                    ResourceRoleAssignment.role == role,
                )
                .all()
            )
            existing_resource_ids = {a.resource_id for a in existing}

            # Create new assignments for resources that don't have one
            new_assignments = []
            for resource_id in unique_resource_ids:
                if resource_id not in existing_resource_ids:
                    new_assignments.append(
                        ResourceRoleAssignment(
                            id=uuid.uuid4(),
                            user_id=user_id,
                            resource_type=resource_type_str,
                            resource_id=resource_id,
                            role=role,
                            assigned_by=assigned_by,
                            reason=reason,
                        )
                    )

            if new_assignments:
                # Bulk insert all new assignments atomically
                self.session.add_all(new_assignments)

                if self.auto_commit:
                    self.session.commit()
                else:
                    self.session.flush()

                # Refresh to get DB-generated values
                for assignment in new_assignments:
                    self.session.refresh(assignment)

                logger.info(
                    f"Bulk added {len(new_assignments)} role assignments: "
                    f"user {user_id} as {role} on {resource_type_str} resources"
                )

            return existing + new_assignments

        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error in bulk add roles: {e}")
            raise

    def remove_role(
        self,
        user_id: uuid.UUID,
        resource_type: ResourceType,
        resource_id: uuid.UUID,
        role: str,
    ) -> bool:
        """Remove a specific role from a user on a resource.

        Args:
            user_id: UUID of the user
            resource_type: ResourceType enum
            resource_id: UUID of the resource
            role: Specific role to remove

        Returns:
            True if deleted, False if not found
        """
        resource_type_str = self._normalize_resource_type(resource_type)
        try:
            assignment = (
                self.session.query(ResourceRoleAssignment)
                .filter(
                    ResourceRoleAssignment.user_id == user_id,
                    ResourceRoleAssignment.resource_type == resource_type_str,
                    ResourceRoleAssignment.resource_id == resource_id,
                    ResourceRoleAssignment.role == role,
                )
                .first()
            )

            if not assignment:
                logger.warning(
                    f"Role assignment not found: user {user_id} with role {role} on {resource_type_str}:{resource_id}"
                )
                return False

            self.session.delete(assignment)

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            logger.info(
                f"Removed role: user {user_id} role {role} on {resource_type_str}:{resource_id}"
            )
            return True
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error removing role: {e}")
            return False

    def remove_all_roles_for_user_on_resource(
        self,
        user_id: uuid.UUID,
        resource_type: ResourceType,
        resource_id: uuid.UUID,
        *,
        raise_on_error: bool = False,
    ) -> int:
        """Remove all role assignments for a user on a specific resource.

        Used when removing a user's access to a specific resource.

        Args:
            user_id: UUID of the user
            resource_type: ResourceType enum
            resource_id: UUID of the resource

        Returns:
            Count of deleted assignments
        """
        resource_type_str = self._normalize_resource_type(resource_type)
        try:
            count = (
                self.session.query(ResourceRoleAssignment)
                .filter(
                    ResourceRoleAssignment.user_id == user_id,
                    ResourceRoleAssignment.resource_type == resource_type_str,
                    ResourceRoleAssignment.resource_id == resource_id,
                )
                .delete()
            )

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            logger.info(
                f"Removed {count} role assignments for user {user_id} on {resource_type_str}:{resource_id}"
            )
            return count
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error removing all roles for user on resource: {e}")
            if raise_on_error:
                raise
            return 0

    def remove_all_assignments_for_user(self, user_id: uuid.UUID) -> int:
        """Remove all role assignments for a user (across all resources).

        Used when removing a user from the system.

        Args:
            user_id: UUID of the user

        Returns:
            Count of deleted assignments
        """
        try:
            count = (
                self.session.query(ResourceRoleAssignment)
                .filter(ResourceRoleAssignment.user_id == user_id)
                .delete()
            )

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            logger.info(f"Removed {count} role assignments for user {user_id}")
            return count
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error removing all assignments for user: {e}")
            return 0

    def remove_all_assignments_for_resource(
        self, resource_type: ResourceType, resource_id: uuid.UUID
    ) -> int:
        """Remove all role assignments for a resource.

        Used when deleting a resource.

        Args:
            resource_type: ResourceType enum
            resource_id: UUID of the resource

        Returns:
            Count of deleted assignments
        """
        resource_type_str = self._normalize_resource_type(resource_type)
        try:
            count = (
                self.session.query(ResourceRoleAssignment)
                .filter(
                    ResourceRoleAssignment.resource_type == resource_type_str,
                    ResourceRoleAssignment.resource_id == resource_id,
                )
                .delete()
            )

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            logger.info(
                f"Removed {count} role assignments for {resource_type_str}:{resource_id}"
            )
            return count
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error removing all assignments for resource: {e}")
            return 0

    def count_owners_for_resource(
        self,
        resource_type: ResourceType,
        resource_id: uuid.UUID,
        owner_role_aliases: Collection[str],
    ) -> int:
        """Count distinct active users with account-admin ownership roles.

        Safety check to prevent removing the last account admin. Ownership role
        policy is supplied by the service layer.

        Args:
            resource_type: ResourceType enum
            resource_id: UUID of the resource
            owner_role_aliases: Role names treated as account ownership roles

        Returns:
            Count of distinct active account-admin users
        """
        if not owner_role_aliases:
            return 0

        resource_type_str = self._normalize_resource_type(resource_type)
        try:
            query = self.session.query(ResourceRoleAssignment).filter(
                ResourceRoleAssignment.resource_type == resource_type_str,
                ResourceRoleAssignment.resource_id == resource_id,
                ResourceRoleAssignment.role.in_(owner_role_aliases),
            )

            if resource_type == ResourceType.ACCOUNT:
                query = query.join(
                    AccountUser,
                    and_(
                        AccountUser.user_id == ResourceRoleAssignment.user_id,
                        AccountUser.account_id == resource_id,
                    ),
                ).filter(AccountUser.status == AccountUserStatus.active)

            return (
                query.with_entities(
                    func.count(func.distinct(ResourceRoleAssignment.user_id))
                ).scalar()
                or 0
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error counting owners for resource: {e}")
            return 0
