"""
RBAC FastAPI Dependencies

Provides dependency injection for permission checking in FastAPI endpoints.

Architecture:
- PermissionChecker: Class-based dependency for query parameter resource IDs
- require_permission: Factory for PermissionChecker
- _create_resource_permission_dependency: Generic factory for path-parameter-based checks
- require_*_permission: Pre-configured factories for specific resource types
"""

from functools import partial
from typing import Any, Callable, Coroutine
from uuid import UUID

from fastapi import Depends, HTTPException, Query, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

import db
from db.repositories.account_user_repository import AccountUserRepository
from services.auth_service.authorization import check_permission
from services.auth_service.resolution import resolve_resource_identifier
from services.auth_types import UserContext, UserRole
from utils.log import logger

# =============================================================================
# GENERIC PERMISSION CHECKING CORE
# =============================================================================


def _check_and_raise(
    user_id: UUID,
    resource_id: str,
    permission: str,
    user_email: str,
    user_role: UserRole,
    session: Session,
) -> None:
    """
    Core permission check logic. Raises HTTPException if permission denied.

    Admin bypass is handled centrally in check_permission().

    Args:
        user_id: User's UUID
        resource_id: Resource identifier (e.g., "projects/uuid")
        permission: Permission to check (e.g., "project.read")
        user_email: User's email for logging
        user_role: User's role for admin bypass
        session: Database session

    Raises:
        HTTPException: 403 if permission denied
    """
    has_permission = check_permission(
        user_id=user_id,
        resource_id=resource_id,
        permission_name=permission,
        session=session,
        user_role=user_role.value if user_role else None,
    )

    if not has_permission:
        logger.warning(
            f"Permission denied: User {user_email} lacks {permission} on {resource_id}",
            extra={"user_id": str(user_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing required permission: {permission}",
            headers={"Content-Type": "application/json"},
        )


def _extract_user_id(current_user: UserContext) -> UUID:
    """
    Extract UUID from UserContext.username.

    Args:
        current_user: Authenticated user context

    Returns:
        User's UUID

    Raises:
        HTTPException: 403 if username is not a valid UUID
    """
    try:
        return UUID(current_user.username)
    except (ValueError, AttributeError) as err:
        logger.error(f"Invalid user ID in UserContext: {current_user.username}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid user credentials",
            headers={"Content-Type": "application/json"},
        ) from err


# =============================================================================
# SPECIALIZED PERMISSION DEPENDENCY FACTORIES
# =============================================================================
# Each factory creates dependencies with explicit parameter names so FastAPI
# can properly inject path parameters. This pattern follows the same approach
# as _create_account_permission_dependency.


def _create_permission_dependency_impl(
    resource_uuid: UUID,
    resource_type: str,
    permission: str,
    current_user: UserContext,
    session: Session,
) -> UserContext:
    """
    Shared implementation for permission checking.

    Args:
        resource_uuid: UUID of the resource from path parameter
        resource_type: Plural resource type (e.g., "projects", "routines")
        permission: Permission name to check
        current_user: Authenticated user context
        session: Database session

    Returns:
        UserContext if permission granted

    Raises:
        HTTPException: 403 if permission denied
    """
    user_id = _extract_user_id(current_user)
    resource_id = f"{resource_type}/{resource_uuid}"

    _check_and_raise(
        user_id=user_id,
        resource_id=resource_id,
        permission=permission,
        user_email=current_user.email,
        user_role=current_user.role,
        session=session,
    )

    return current_user


# -----------------------------------------------------------------------------
# Account Permission (special - uses account_name string, not UUID)
# -----------------------------------------------------------------------------


def require_account_permission(
    permission: str, auth_dependency: Callable
) -> Callable[..., Coroutine[Any, Any, UserContext]]:
    """Create a permission dependency for account resources."""

    async def dependency(
        account_name: str,
        current_user: UserContext = Depends(auth_dependency),
        session: Session = Depends(db.get_db),
    ) -> UserContext:
        user_id = _extract_user_id(current_user)
        resource_id = f"accounts/{account_name}"

        await run_in_threadpool(
            partial(
                _check_and_raise,
                user_id=user_id,
                resource_id=resource_id,
                permission=permission,
                user_email=current_user.email,
                user_role=current_user.role,
                session=session,
            )
        )

        return current_user

    return dependency


def require_account_membership(
    auth_dependency: Callable,
) -> Callable[..., Coroutine[Any, Any, UserContext]]:
    """
    Create a membership-only dependency for account resources.

    Unlike require_account_permission, this only checks that the user is a member
    of the account (via account_users table) without requiring specific permissions.
    Useful for endpoints that any team member should access regardless of role.

    Args:
        auth_dependency: Authentication dependency (e.g., authenticate_user)

    Returns:
        Dependency that validates account membership
    """

    async def dependency(
        account_name: str,
        current_user: UserContext = Depends(auth_dependency),
        session: Session = Depends(db.get_db),
    ) -> UserContext:
        user_id = _extract_user_id(current_user)

        # Admin bypass
        if current_user.role and current_user.role.value == "Admin":
            return current_user

        def check_membership() -> None:
            # Resolve account name to UUID
            try:
                account_id = resolve_resource_identifier(
                    "accounts", account_name, session
                )
            except ValueError as e:
                logger.warning(f"Account resolution failed: {e}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Account '{account_name}' not found",
                    headers={"Content-Type": "application/json"},
                ) from e

            # Check membership
            account_user_repo = AccountUserRepository(session, auto_commit=False)
            if not account_user_repo.is_member(user_id, account_id):
                logger.warning(
                    f"Membership denied: User {current_user.email} is not a member of {account_name}"
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User is not a member of this account",
                    headers={"Content-Type": "application/json"},
                )

        await run_in_threadpool(check_membership)

        return current_user

    return dependency


# -----------------------------------------------------------------------------
# Project Permission
# -----------------------------------------------------------------------------


def require_project_permission(
    permission: str, auth_dependency: Callable
) -> Callable[..., Coroutine[Any, Any, UserContext]]:
    """Create a permission dependency for project resources."""

    async def dependency(
        project_id: UUID,
        current_user: UserContext = Depends(auth_dependency),
        session: Session = Depends(db.get_db),
    ) -> UserContext:
        return await run_in_threadpool(
            partial(
                _create_permission_dependency_impl,
                project_id,
                "projects",
                permission,
                current_user,
                session,
            )
        )

    return dependency


# -----------------------------------------------------------------------------
# Checklist Permission
# -----------------------------------------------------------------------------


def require_checklist_permission(
    permission: str, auth_dependency: Callable
) -> Callable[..., Coroutine[Any, Any, UserContext]]:
    """Create a permission dependency for checklist resources."""

    async def dependency(
        checklist_id: UUID,
        current_user: UserContext = Depends(auth_dependency),
        session: Session = Depends(db.get_db),
    ) -> UserContext:
        return await run_in_threadpool(
            partial(
                _create_permission_dependency_impl,
                checklist_id,
                "checklists",
                permission,
                current_user,
                session,
            )
        )

    return dependency


# -----------------------------------------------------------------------------
# Agent Permission
# -----------------------------------------------------------------------------


def require_agent_permission(
    permission: str, auth_dependency: Callable
) -> Callable[..., Coroutine[Any, Any, UserContext]]:
    """Create a permission dependency for agent resources."""

    async def dependency(
        agent_id: UUID,
        current_user: UserContext = Depends(auth_dependency),
        session: Session = Depends(db.get_db),
    ) -> UserContext:
        return await run_in_threadpool(
            partial(
                _create_permission_dependency_impl,
                agent_id,
                "agents",
                permission,
                current_user,
                session,
            )
        )

    return dependency


# -----------------------------------------------------------------------------
# History Permission
# -----------------------------------------------------------------------------


def require_history_permission(
    permission: str, auth_dependency: Callable
) -> Callable[..., Coroutine[Any, Any, UserContext]]:
    """Create a permission dependency for history/changelog resources."""

    async def dependency(
        change_log_id: UUID,
        current_user: UserContext = Depends(auth_dependency),
        session: Session = Depends(db.get_db),
    ) -> UserContext:
        return await run_in_threadpool(
            partial(
                _create_permission_dependency_impl,
                change_log_id,
                "histories",
                permission,
                current_user,
                session,
            )
        )

    return dependency


# -----------------------------------------------------------------------------
# Feedback Permission
# -----------------------------------------------------------------------------


def require_feedback_permission(
    permission: str, auth_dependency: Callable
) -> Callable[..., Coroutine[Any, Any, UserContext]]:
    """Create a permission dependency for feedback resources."""

    async def dependency(
        feedback_id: UUID,
        current_user: UserContext = Depends(auth_dependency),
        session: Session = Depends(db.get_db),
    ) -> UserContext:
        return await run_in_threadpool(
            partial(
                _create_permission_dependency_impl,
                feedback_id,
                "feedbacks",
                permission,
                current_user,
                session,
            )
        )

    return dependency


# -----------------------------------------------------------------------------
# Campaign Permission
# -----------------------------------------------------------------------------


def require_campaign_permission(
    permission: str, auth_dependency: Callable
) -> Callable[..., Coroutine[Any, Any, UserContext]]:
    """Create a permission dependency for campaign resources."""

    async def dependency(
        campaign_id: UUID,
        current_user: UserContext = Depends(auth_dependency),
        session: Session = Depends(db.get_db),
    ) -> UserContext:
        return await run_in_threadpool(
            partial(
                _create_permission_dependency_impl,
                campaign_id,
                "campaigns",
                permission,
                current_user,
                session,
            )
        )

    return dependency


# -----------------------------------------------------------------------------
# Knowledge Permission
# -----------------------------------------------------------------------------


def require_knowledge_permission(
    permission: str, auth_dependency: Callable
) -> Callable[..., Coroutine[Any, Any, UserContext]]:
    """Create a permission dependency for knowledge resources."""

    async def dependency(
        knowledge_id: UUID,
        current_user: UserContext = Depends(auth_dependency),
        session: Session = Depends(db.get_db),
    ) -> UserContext:
        return await run_in_threadpool(
            partial(
                _create_permission_dependency_impl,
                knowledge_id,
                "knowledges",
                permission,
                current_user,
                session,
            )
        )

    return dependency


# -----------------------------------------------------------------------------
# Subscription Permission
# -----------------------------------------------------------------------------


def require_subscription_permission(
    permission: str, auth_dependency: Callable
) -> Callable[..., Coroutine[Any, Any, UserContext]]:
    """Create a permission dependency for subscription resources."""

    async def dependency(
        subscription_id: UUID,
        current_user: UserContext = Depends(auth_dependency),
        session: Session = Depends(db.get_db),
    ) -> UserContext:
        return await run_in_threadpool(
            partial(
                _create_permission_dependency_impl,
                subscription_id,
                "subscriptions",
                permission,
                current_user,
                session,
            )
        )

    return dependency


# -----------------------------------------------------------------------------
# Routine Permission
# -----------------------------------------------------------------------------


def require_routine_permission(
    permission: str, auth_dependency: Callable
) -> Callable[..., Coroutine[Any, Any, UserContext]]:
    """Create a permission dependency for routine resources."""

    async def dependency(
        routine_id: UUID,
        current_user: UserContext = Depends(auth_dependency),
        session: Session = Depends(db.get_db),
    ) -> UserContext:
        return await run_in_threadpool(
            partial(
                _create_permission_dependency_impl,
                routine_id,
                "routines",
                permission,
                current_user,
                session,
            )
        )

    return dependency


# -----------------------------------------------------------------------------
# Execution Permission
# -----------------------------------------------------------------------------


def require_execution_permission(
    permission: str, auth_dependency: Callable
) -> Callable[..., Coroutine[Any, Any, UserContext]]:
    """Create a permission dependency for execution resources."""

    async def dependency(
        execution_id: UUID,
        current_user: UserContext = Depends(auth_dependency),
        session: Session = Depends(db.get_db),
    ) -> UserContext:
        return await run_in_threadpool(
            partial(
                _create_permission_dependency_impl,
                execution_id,
                "executions",
                permission,
                current_user,
                session,
            )
        )

    return dependency


# -----------------------------------------------------------------------------
# Submission Permission
# -----------------------------------------------------------------------------


def require_submission_permission(
    permission: str, auth_dependency: Callable
) -> Callable[..., Coroutine[Any, Any, UserContext]]:
    """Create a permission dependency for submission resources."""

    async def dependency(
        submission_id: UUID,
        current_user: UserContext = Depends(auth_dependency),
        session: Session = Depends(db.get_db),
    ) -> UserContext:
        return await run_in_threadpool(
            partial(
                _create_permission_dependency_impl,
                submission_id,
                "submissions",
                permission,
                current_user,
                session,
            )
        )

    return dependency


# =============================================================================
# LEGACY CLASS-BASED PERMISSION CHECKER
# =============================================================================


class PermissionChecker:
    """
    FastAPI dependency for permission checking via query parameter.

    NOTE: For most use cases, prefer the factory functions like
    require_project_permission(), require_checklist_permission(), etc.
    which automatically extract resource IDs from path parameters.

    This class is useful when the resource_id must be passed as a query parameter.

    Usage:
        @router.post("/admin/actions")
        async def perform_action(
            context: UserContext = Depends(
                PermissionChecker("checklist.write", authenticate_user)
            ),
        ):
            # Client must pass ?resource_id=checklists/uuid-here
            pass
    """

    def __init__(self, required_permission: str, auth_dependency: Callable):
        self.required_permission = required_permission
        self.auth_dependency = auth_dependency

    def __call__(self) -> Callable:
        required_permission = self.required_permission
        auth_dependency = self.auth_dependency

        async def permission_dependency(
            resource_id: str = Query(
                ...,
                description="Resource ID in format 'resource_type/uuid'",
                pattern=r"^[a-z]+/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            ),
            current_user: UserContext = Depends(auth_dependency),
            session: Session = Depends(db.get_db),
        ) -> UserContext:
            try:
                user_id = _extract_user_id(current_user)
            except HTTPException:
                # Re-raise original HTTPException for consistency with factory functions
                raise

            try:
                await run_in_threadpool(
                    partial(
                        _check_and_raise,
                        user_id=user_id,
                        resource_id=resource_id,
                        permission=required_permission,
                        user_email=current_user.email,
                        user_role=current_user.role,
                        session=session,
                    )
                )
            except HTTPException:
                raise
            except ValueError as err:
                logger.error(f"Invalid resource_id format: {err}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid resource_id format: {err!s}",
                    headers={"Content-Type": "application/json"},
                ) from err

            return current_user

        return permission_dependency


def require_permission(permission: str, auth_dependency: Callable) -> PermissionChecker:
    """
    Create a query-parameter-based permission checker dependency.

    For path-parameter-based checking, use the specific factories like
    require_project_permission(), require_routine_permission(), etc.

    Usage:
        @router.post("/admin/projects")
        async def create_project(
            user = Depends(require_permission("project.create", authenticate_user)),
        ):
            # Client must pass ?resource_id=accounts/uuid
            pass
    """
    return PermissionChecker(permission, auth_dependency)
