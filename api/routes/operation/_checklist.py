"""
Checklist Operation Routes

This module handles authorization and delegates to the checklist_service for business logic.
"""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from api.schemas.admin.checklist import (
    Checklist,
    CreateChecklistRequest,
    ListChecklistsResponse,
    UpdateChecklistRequest,
)
from services import account_service, checklist_service, project_service
from services.auth_service import check_permission
from services.auth_types import UserContext, UserRole


def _authorize_project_access(
    session: Session,
    project_id: UUID,
    context: UserContext,
    permission: str = "project.read",
) -> None:
    """
    Authorize user access to a project using RBAC.

    Raises 403 FORBIDDEN if project/account not found or user lacks permission.
    This prevents information leakage about resource existence.

    Args:
        session: Database session
        project_id: Project UUID
        context: User authentication context
        permission: The permission to check (default: project.read)

    Raises:
        HTTPException: 403 if authorization fails
    """
    project = project_service.get_project(session, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    account = account_service.get_account_by_id(session, project.account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    # Admin has full access
    if context.role == UserRole.Admin:
        return
    # Check permission on project
    user_id = UUID(context.username)
    if not check_permission(user_id, f"projects/{project_id}", permission, session):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing required permission: {permission}",
            headers={"Content-Type": "application/json"},
        )


def _authorize_checklist_access(
    session: Session,
    checklist: Checklist,
    context: UserContext,
    permission: str = "project.read",
) -> None:
    """
    Authorize user access to a checklist via its project using RBAC.

    Raises 403 FORBIDDEN if project/account not found or user lacks permission.
    This prevents information leakage about resource existence.

    Args:
        session: Database session
        checklist: Checklist schema object
        context: User authentication context
        permission: The permission to check (default: project.read)

    Raises:
        HTTPException: 403 if authorization fails
    """
    if checklist.project_id:
        project = project_service.get_project(session, UUID(checklist.project_id))
        if not project:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

        account = account_service.get_account_by_id(session, project.account_id)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

        # Admin has full access
        if context.role == UserRole.Admin:
            return
        # Check permission on project
        user_id = UUID(context.username)
        if not check_permission(
            user_id, f"projects/{checklist.project_id}", permission, session
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {permission}",
                headers={"Content-Type": "application/json"},
            )


async def create_checklist(
    project_id: UUID,
    checklist_request: CreateChecklistRequest,
    context: UserContext,
    session: Session,
) -> Checklist:
    """
    Create a new checklist for a project.
    Authorization is handled by require_project_permission in route decorator.
    """
    # Delegate to service for business logic
    return await checklist_service.create_checklist(
        project_id, checklist_request, context, session
    )


async def get_checklist(
    checklist_id: UUID,
    context: UserContext,
    session: Session,
) -> Checklist:
    """
    Get a checklist by ID.
    Authorization handled by require_checklist_permission in route decorator.
    """
    return await checklist_service.get_checklist(checklist_id, context, session)


async def list_checklists_by_project(
    project_id: UUID,
    context: UserContext,
    session: Session,
    exclude: UUID | None = None,
) -> ListChecklistsResponse:
    """
    List all checklists for a specific project.
    Authorization is handled by require_project_permission in route decorator.
    """
    # Delegate to service for business logic
    return await checklist_service.list_checklists_by_project(
        project_id, context, session, exclude
    )


async def update_checklist(
    checklist_id: UUID,
    update_request: UpdateChecklistRequest,
    context: UserContext,
    session: Session,
) -> Checklist:
    """
    Update a checklist by ID.
    Authorization handled by require_checklist_permission in route decorator.
    """
    return await checklist_service.update_checklist(
        checklist_id, update_request, context, session
    )


async def delete_checklist(
    checklist_id: UUID,
    context: UserContext,
    session: Session,
) -> None:
    """
    Delete a checklist by ID.
    Authorization handled by require_checklist_permission in route decorator.
    """
    await checklist_service.delete_checklist(checklist_id, context, session)
