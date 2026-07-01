"""Store-scope helpers for customer RBAC.

These helpers answer "which stores can this user access for this permission?"
so account-scoped list routes can filter store-backed data consistently.
"""

from collections.abc import Collection, Iterable
from uuid import UUID

from sqlalchemy.orm import Session

from db.repositories.account_user_repository import AccountUserRepository
from db.repositories.project_repository import ProjectRepository
from db.repositories.resource_role_assignment_repository import (
    ResourceRoleAssignmentRepository,
    ResourceType,
)
from services.auth_service.authorization import get_merged_permissions
from services.auth_service.config import ACCOUNT_ADMIN_ROLE_ALIASES
from services.auth_types import UserRole


class ProjectScopeForbiddenError(PermissionError):
    """Raised when a caller explicitly requests projects outside their scope."""

    def __init__(
        self,
        denied_project_ids: Collection[UUID],
        accessible_project_ids: Collection[UUID],
    ) -> None:
        self.denied_project_ids = frozenset(denied_project_ids)
        self.accessible_project_ids = frozenset(accessible_project_ids)
        super().__init__("Requested project_ids are outside the caller's scope")


def _roles_grant_permission(roles: Iterable[str], permission: str) -> bool:
    permissions = get_merged_permissions(list(roles))
    return "*" in permissions or permission in permissions


def get_account_project_ids(session: Session, account_id: UUID) -> frozenset[UUID]:
    """Return all project IDs that belong to an account."""
    project_repo = ProjectRepository(session, auto_commit=False)
    return frozenset(
        project.id for project in project_repo.get_projects_by_account_id(account_id)
    )


def get_accessible_project_ids(
    session: Session,
    user_id: UUID,
    account_id: UUID,
    permission: str,
    *,
    user_role: str | None = None,
) -> frozenset[UUID]:
    """Return account project IDs where the user has the requested permission.

    Account Admin aliases grant every project in the account. Store-scoped roles
    grant only the assigned project when the role includes ``permission``.
    Internal Palona Admin bypasses customer RBAC but remains bounded to the
    account's projects.
    """
    if user_role == UserRole.Admin.value:
        return get_account_project_ids(session, account_id)

    account_user_repo = AccountUserRepository(session, auto_commit=False)
    if not account_user_repo.is_member(user_id, account_id):
        return frozenset()

    role_repo = ResourceRoleAssignmentRepository(session, auto_commit=False)
    account_roles = role_repo.get_roles_for_resource(
        user_id=user_id,
        resource_type=ResourceType.ACCOUNT,
        resource_id=account_id,
    )
    account_admin_roles = [
        role for role in account_roles if role in ACCOUNT_ADMIN_ROLE_ALIASES
    ]
    if _roles_grant_permission(account_admin_roles, permission):
        return get_account_project_ids(session, account_id)

    account_project_ids = get_account_project_ids(session, account_id)
    project_assignments = role_repo.get_assignments_for_resources(
        ResourceType.PROJECT, list(account_project_ids)
    )

    return frozenset(
        assignment.resource_id
        for assignment in project_assignments
        if assignment.user_id == user_id
        and _roles_grant_permission([assignment.role], permission)
    )


def authorize_requested_project_ids(
    requested_project_ids: Collection[UUID] | None,
    accessible_project_ids: Collection[UUID],
) -> list[UUID]:
    """Validate an optional project filter against accessible project IDs.

    ``None`` means the caller did not supply a project filter, so the effective
    scope defaults to all accessible projects. Explicit out-of-scope IDs raise
    ``ProjectScopeForbiddenError`` for callers to convert to HTTP 403.
    """
    accessible_set = frozenset(accessible_project_ids)
    if requested_project_ids is None:
        return sorted(accessible_set, key=str)

    unique_requested: list[UUID] = []
    seen: set[UUID] = set()
    for project_id in requested_project_ids:
        if project_id not in seen:
            seen.add(project_id)
            unique_requested.append(project_id)

    denied_project_ids = [
        project_id
        for project_id in unique_requested
        if project_id not in accessible_set
    ]
    if denied_project_ids:
        raise ProjectScopeForbiddenError(denied_project_ids, accessible_set)

    return unique_requested


def resolve_project_scope(
    session: Session,
    user_id: UUID,
    account_id: UUID,
    permission: str,
    requested_project_ids: Collection[UUID] | None = None,
    *,
    user_role: str | None = None,
) -> list[UUID]:
    """Return the effective project IDs for an account-scoped request."""
    accessible_project_ids = get_accessible_project_ids(
        session=session,
        user_id=user_id,
        account_id=account_id,
        permission=permission,
        user_role=user_role,
    )
    return authorize_requested_project_ids(
        requested_project_ids=requested_project_ids,
        accessible_project_ids=accessible_project_ids,
    )
