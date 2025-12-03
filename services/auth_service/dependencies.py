"""
RBAC FastAPI Dependencies

Provides dependency injection for permission checking in FastAPI endpoints.
"""

from typing import Any, Callable, Coroutine
from uuid import UUID

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

import db
from services.auth_service.authorization import check_permission
from services.auth_types import UserContext, UserRole
from utils.log import logger


class PermissionChecker:
    """
    FastAPI dependency for permission checking (V1 - multi-resource support).

    Combines authentication and authorization into a single dependency.
    Automatically chains with the provided auth_dependency to verify both
    the user's identity and their permissions on the specified resource.

    Requires resource_id as a query parameter in format "resource_type/uuid".

    Note: For most use cases, prefer the specialized helper functions like
    require_checklist_permission(), require_project_permission(), etc. which
    automatically extract resource IDs from path parameters.

    Usage:
        from api.routes.admin._auth import authenticate_user
        from services.auth_service import PermissionChecker

        # Client must pass ?resource_id=checklists/uuid-here
        @router.post("/admin/actions")
        async def perform_action(
            context: UserContext = Depends(PermissionChecker("checklist.write", authenticate_user)),
            session: Session = Depends(db.get_db)
        ):
            # context is now authenticated AND has checklist.write permission
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
            resource_id: str = Query(
                ...,
                description="Resource ID in format 'resource_type/uuid' (e.g., 'accounts/xxx', 'checklists/yyy')",
                pattern="^(accounts|projects|agents|checklists|plans|data)/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            ),
            current_user: UserContext = Depends(auth_dependency),
            session: Session = Depends(db.get_db),
        ) -> UserContext:
            """
            Check if current user has required permission on resource.

            Args:
                resource_id: Resource identifier in format "resource_type/uuid"
                current_user: Authenticated user (injected by FastAPI via auth_dependency)
                session: Database session

            Returns:
                UserContext if permission granted

            Raises:
                HTTPException: 400 if resource_id format invalid
                HTTPException: 403 if permission denied
            """
            # Extract user_id from UserContext username (which is UUID)
            try:
                user_id = UUID(current_user.username)
            except (ValueError, AttributeError) as err:
                logger.error(f"Invalid user ID in UserContext: {current_user.username}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid user credentials",
                    headers={"Content-Type": "application/json"},
                ) from err

            # Check permission (with validation)
            try:
                has_permission = check_permission(
                    user_id=user_id,
                    resource_id=resource_id,
                    permission_name=required_permission,
                    session=session,
                )
            except ValueError as err:
                # Invalid resource_id format - return HTTP 400
                logger.error(f"Invalid resource_id format: {err}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid resource_id format: {str(err)}",
                    headers={"Content-Type": "application/json"},
                ) from err

            if not has_permission:
                logger.warning(
                    f"Permission denied: User {user_id} lacks {required_permission} on {resource_id}"
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


def require_account_permission(
    permission: str, auth_dependency: Callable
) -> Callable[..., Coroutine[Any, Any, UserContext]]:
    """
    Factory for account-level permission checking.

    Creates a FastAPI dependency that automatically extracts account name from
    path parameters, constructs the resource_id, and checks permissions.
    Supports both legacy (account membership) and RBAC modes via feature flag.

    Args:
        permission: Permission name (e.g., "project.create", "account.read")
        auth_dependency: Authentication dependency (e.g., authenticate_user)

    Returns:
        FastAPI dependency function that checks account permissions

    Usage:
        from api.routes.admin._auth import authenticate_user

        # Works with account name
        @router.get("/accounts/{account_name}/settings")
        async def get_settings(
            account_name: str,  # Can be "palona" or UUID
            context: UserContext = Depends(
                require_account_permission("account.read", authenticate_user)
            ),
            session: Session = Depends(db.get_db)
        ):
            # context is authenticated AND has account.read/write permission
            pass
    """
    # Import here to avoid circular import
    from services.auth_service.feature_flags import is_rbac_enabled

    async def dependency(
        account_name: str,
        current_user: UserContext = Depends(auth_dependency),
        session: Session = Depends(db.get_db),
    ) -> UserContext:
        # Extract user_id from UserContext
        try:
            user_id = UUID(current_user.username)
        except (ValueError, AttributeError) as err:
            logger.error(f"Invalid user ID in UserContext: {current_user.username}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid user credentials",
                headers={"Content-Type": "application/json"},
            ) from err

        # Legacy mode: fall back to account membership check
        if not is_rbac_enabled():
            if account_name not in current_user.account_names:
                if current_user.role != UserRole.Admin:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="User does not have permission for the requested account",
                        headers={"Content-Type": "application/json"},
                    )
            return current_user

        # RBAC mode: check permission via RBAC system
        resource_id = f"accounts/{account_name}"

        has_permission = check_permission(
            user_id=user_id,
            resource_id=resource_id,
            permission_name=permission,
            session=session,
        )

        if not has_permission:
            logger.warning(
                f"Permission denied: User {user_id} lacks {permission} on {resource_id}"
            )

        # TODO: admin override should be explicit
        is_admin = current_user.role == UserRole.Admin

        if not has_permission and not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {permission}",
                headers={"Content-Type": "application/json"},
            )

        return current_user

    return dependency


def require_project_permission(
    permission: str, auth_dependency: Callable
) -> Callable[..., Coroutine[Any, Any, UserContext]]:
    """
    Factory for project-level permission checking.

    Creates a FastAPI dependency that automatically extracts project_id from
    path parameters, constructs the resource_id, and checks permissions.
    Supports both legacy (account membership) and RBAC modes via feature flag.

    Args:
        permission: Permission name (e.g., "project.read")
        auth_dependency: Authentication dependency (e.g., authenticate_user)

    Returns:
        FastAPI dependency function that checks project permissions

    Usage:
        from api.routes.admin._auth import authenticate_user

        @router.get("/projects/{project_id}/checklists")
        async def list_checklists(
            project_id: UUID,
            context: UserContext = Depends(
                require_project_permission("project.read", authenticate_user)
            ),
            session: Session = Depends(db.get_db)
        ):
            # context is authenticated AND has project.read permission
            pass
    """
    # Import here to avoid circular import
    from services.auth_service.feature_flags import is_rbac_enabled

    async def dependency(
        project_id: UUID,
        current_user: UserContext = Depends(auth_dependency),
        session: Session = Depends(db.get_db),
    ) -> UserContext:
        # Extract user_id from UserContext
        try:
            user_id = UUID(current_user.username)
        except (ValueError, AttributeError) as err:
            logger.error(f"Invalid user ID in UserContext: {current_user.username}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid user credentials",
                headers={"Content-Type": "application/json"},
            ) from err

        # Legacy mode: look up project's account and check membership
        if not is_rbac_enabled():
            from services import project_service

            project = project_service.get_project(session, project_id)
            if not project:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Project not found",
                    headers={"Content-Type": "application/json"},
                )
            account_name = project.account.name
            if account_name not in current_user.account_names:
                if current_user.role != UserRole.Admin:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="User does not have permission for the requested account",
                        headers={"Content-Type": "application/json"},
                    )
            return current_user

        # RBAC mode: check permission via RBAC system
        resource_id = f"projects/{project_id}"

        has_permission = check_permission(
            user_id=user_id,
            resource_id=resource_id,
            permission_name=permission,
            session=session,
        )

        if not has_permission:
            logger.warning(
                f"Permission denied: User {user_id} lacks {permission} on {resource_id}"
            )

        is_admin = current_user.role == UserRole.Admin

        if not has_permission and not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {permission}",
                headers={"Content-Type": "application/json"},
            )

        return current_user

    return dependency


def require_checklist_permission(
    permission: str, auth_dependency: Callable
) -> Callable[..., Coroutine[Any, Any, UserContext]]:
    """
    Factory for checklist-level permission checking.

    Creates a FastAPI dependency that automatically extracts checklist_id from
    path parameters, constructs the resource_id, and checks permissions.

    Args:
        permission: Permission name (e.g., "checklist.read")
        auth_dependency: Authentication dependency (e.g., authenticate_user)

    Returns:
        FastAPI dependency function that checks checklist permissions

    Usage:
        from api.routes.admin._auth import authenticate_user

        @router.get("/checklists/{checklist_id}")
        async def get_checklist(
            checklist_id: UUID,
            context: UserContext = Depends(
                require_checklist_permission("checklist.read", authenticate_user)
            ),
            session: Session = Depends(db.get_db)
        ):
            # context is authenticated AND has checklist.read permission
            pass
    """

    async def dependency(
        checklist_id: UUID,
        current_user: UserContext = Depends(auth_dependency),
        session: Session = Depends(db.get_db),
    ) -> UserContext:
        # Extract user_id from UserContext
        try:
            user_id = UUID(current_user.username)
        except (ValueError, AttributeError) as err:
            logger.error(f"Invalid user ID in UserContext: {current_user.username}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid user credentials",
                headers={"Content-Type": "application/json"},
            ) from err

        # Construct resource_id
        resource_id = f"checklists/{checklist_id}"

        # Check permission
        has_permission = check_permission(
            user_id=user_id,
            resource_id=resource_id,
            permission_name=permission,
            session=session,
        )

        if not has_permission:
            logger.warning(
                f"Permission denied: User {user_id} lacks {permission} on {resource_id}"
            )

        is_admin = current_user.role == UserRole.Admin

        if not has_permission and not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {permission}",
                headers={"Content-Type": "application/json"},
            )

        return current_user

    return dependency


def require_agent_permission(
    permission: str, auth_dependency: Callable
) -> Callable[..., Coroutine[Any, Any, UserContext]]:
    """
    Factory for agent-level permission checking.

    Creates a FastAPI dependency that automatically extracts agent_id from
    path parameters, constructs the resource_id, and checks permissions.
    Supports both legacy (account membership) and RBAC modes via feature flag.

    Args:
        permission: Permission name (e.g., "agent.read")
        auth_dependency: Authentication dependency (e.g., authenticate_user)

    Returns:
        FastAPI dependency function that checks agent permissions

    Usage:
        from api.routes.admin._auth import authenticate_user

        @router.get("/agents/{agent_id}")
        async def get_agent(
            agent_id: UUID,
            context: UserContext = Depends(
                require_agent_permission("agent.read", authenticate_user)
            ),
            session: Session = Depends(db.get_db)
        ):
            # context is authenticated AND has agent.read permission
            pass
    """
    # Import here to avoid circular import
    from services.auth_service.feature_flags import is_rbac_enabled

    async def dependency(
        agent_id: UUID,
        current_user: UserContext = Depends(auth_dependency),
        session: Session = Depends(db.get_db),
    ) -> UserContext:
        # Extract user_id from UserContext
        try:
            user_id = UUID(current_user.username)
        except (ValueError, AttributeError) as err:
            logger.error(f"Invalid user ID in UserContext: {current_user.username}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid user credentials",
                headers={"Content-Type": "application/json"},
            ) from err

        # Legacy mode: look up agent's account and check membership
        if not is_rbac_enabled():
            from services import agent_service

            agent = agent_service.get_agent(session, agent_id)
            if not agent:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Agent not found",
                    headers={"Content-Type": "application/json"},
                )
            account_name = agent.account.name
            if account_name not in current_user.account_names:
                if current_user.role != UserRole.Admin:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="User does not have permission for the requested account",
                        headers={"Content-Type": "application/json"},
                    )
            return current_user

        # RBAC mode: check permission via RBAC system
        resource_id = f"agents/{agent_id}"

        has_permission = check_permission(
            user_id=user_id,
            resource_id=resource_id,
            permission_name=permission,
            session=session,
        )

        if not has_permission:
            logger.warning(
                f"Permission denied: User {user_id} lacks {permission} on {resource_id}"
            )

        is_admin = current_user.role == UserRole.Admin

        if not has_permission and not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {permission}",
                headers={"Content-Type": "application/json"},
            )

        return current_user

    return dependency


def require_resource_permission(
    permission: str, resource_type: str, param_name: str, auth_dependency: Callable
) -> Callable[..., Coroutine[Any, Any, UserContext]]:
    """
    Generic factory for resource-level permission checking.

    Creates a FastAPI dependency that extracts a resource ID from request parameters
    using the specified param_name, constructs the resource_id, and checks permissions.

    Args:
        permission: Permission name (e.g., "checklist.read")
        resource_type: Resource type (e.g., "checklists", "projects")
        param_name: Name of the path/query parameter containing the resource UUID
        auth_dependency: Authentication dependency (e.g., authenticate_user)

    Returns:
        FastAPI dependency function that checks resource permissions

    Usage:
        from api.routes.admin._auth import authenticate_user

        # For custom resource types not covered by specific helpers
        @router.get("/plans/{plan_id}")
        async def get_plan(
            plan_id: UUID,
            context: UserContext = Depends(
                require_resource_permission("plan.read", "plans", "plan_id", authenticate_user)
            ),
            session: Session = Depends(db.get_db)
        ):
            # context is authenticated AND has plan.read permission
            pass
    """

    async def dependency(
        current_user: UserContext = Depends(auth_dependency),
        session: Session = Depends(db.get_db),
        **path_params,
    ) -> UserContext:
        # Extract resource_id from path parameters
        if param_name not in path_params:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Missing required path parameter: {param_name}",
                headers={"Content-Type": "application/json"},
            )

        resource_uuid = path_params[param_name]

        # Extract user_id from UserContext
        try:
            user_id = UUID(current_user.username)
        except (ValueError, AttributeError) as err:
            logger.error(f"Invalid user ID in UserContext: {current_user.username}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid user credentials",
                headers={"Content-Type": "application/json"},
            ) from err

        # Construct resource_id
        resource_id = f"{resource_type}/{resource_uuid}"

        # Check permission
        has_permission = check_permission(
            user_id=user_id,
            resource_id=resource_id,
            permission_name=permission,
            session=session,
        )

        if not has_permission:
            logger.warning(
                f"Permission denied: User {user_id} lacks {permission} on {resource_id}"
            )

        is_admin = current_user.role == UserRole.Admin

        if not has_permission and not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {permission}",
                headers={"Content-Type": "application/json"},
            )

        return current_user

    return dependency
