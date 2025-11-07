"""
RBAC FastAPI Dependencies

Provides dependency injection for permission checking in FastAPI endpoints.
"""

from typing import Callable
from uuid import UUID

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

import db
from services.auth_service.authorization import check_permission
from services.auth_types import UserContext
from utils.log import logger


class PermissionChecker:
    """
    FastAPI dependency for permission checking (V1 - account-level).

    Combines authentication and authorization into a single dependency.
    Automatically chains with the provided auth_dependency to verify both
    the user's identity and their permissions on the specified account.

    Usage:
        from api.routes.admin._auth import authenticate_user
        from services.auth_service import PermissionChecker

        @router.post("/admin/projects")
        async def create_project(
            account_id: UUID,
            context: UserContext = Depends(PermissionChecker("project.create", authenticate_user)),
            session: Session = Depends(db.get_db)
        ):
            # context is now authenticated AND has project.create permission
            pass
    """

    def __init__(self, required_permission: str, auth_dependency: Callable):
        """
        Initialize the permission checker.

        Args:
            required_permission: Permission name (e.g., 'project.create')
            auth_dependency: Authentication dependency function (e.g., authenticate_user)
        """
        self.required_permission = required_permission
        self.auth_dependency = auth_dependency

    def __call__(self) -> Callable:
        """
        Returns the actual dependency function with auth_dependency captured in closure.

        This method is called once when the dependency is registered.
        It returns a function that FastAPI will call on each request.
        """
        # Capture self in closure to avoid "self not defined" issues with Depends()
        required_permission = self.required_permission
        auth_dependency = self.auth_dependency

        async def permission_dependency(
            account_id: UUID = Query(
                ..., description="Account ID to check permissions for"
            ),
            current_user: UserContext = Depends(auth_dependency),
            session: Session = Depends(db.get_db),
        ) -> UserContext:
            """
            Check if current user has required permission on account.

            Args:
                account_id: Account ID to check permission on
                current_user: Authenticated user (injected by FastAPI via auth_dependency)
                session: Database session

            Returns:
                UserContext if permission granted

            Raises:
                HTTPException: 403 if permission denied
            """
            # Extract user_id from UserContext username (which is UUID)
            try:
                user_id = UUID(current_user.username)
            except (ValueError, AttributeError) as err:
                logger.error(f"Invalid user ID in UserContext: {current_user.username}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Invalid user credentials",
                    headers={"Content-Type": "application/json"},
                ) from err

            # Check permission
            has_permission = check_permission(
                user_id=user_id,
                account_id=account_id,
                permission_name=required_permission,
                session=session,
            )

            if not has_permission:
                logger.warning(
                    f"Permission denied: User {user_id} lacks {required_permission} on account {account_id}"
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Missing required permission: {required_permission}",
                    headers={"Content-Type": "application/json"},
                )

            return current_user

        return permission_dependency


def require_permission(permission: str, auth_dependency: Callable) -> PermissionChecker:
    """
    Create a permission checker dependency.

    Combines authentication and authorization into a single dependency.
    Automatically chains with the provided auth_dependency to verify both
    the user's identity and their permissions on the specified account.

    Usage:
        from api.routes.admin._auth import authenticate_user

        @router.post("/admin/projects")
        async def create_project(
            account_id: UUID,
            user = Depends(require_permission("project.create", authenticate_user)),
            session: Session = Depends(db.get_db)
        ):
            # user is now authenticated AND has project.create permission
            pass
    """
    return PermissionChecker(permission, auth_dependency)
