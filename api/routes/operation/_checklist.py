"""
Checklist Operation Routes

This module handles authorization and delegates to the checklist_service for business logic.
"""

from datetime import datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from api.schemas.admin.checklist import (
    BatchChecklistHistoryResponse,
    Checklist,
    ChecklistHistoryResponse,
    CreateChecklistRequest,
    ListChecklistsResponse,
    UpdateChecklistRequest,
)
from services import account_service, checklist_service, project_service
from services.auth_service import check_permission, is_rbac_enabled
from services.auth_types import UserContext, UserRole


def _authorize_project_access(
    session: Session,
    project_id: UUID,
    context: UserContext,
    permission: str = "project.read",
) -> None:
    """
    Authorize user access to a project using RBAC or legacy mode.

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

    if not is_rbac_enabled():
        # Legacy: check account membership
        if account.name not in context.account_names:
            if context.role != UserRole.Admin:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied",
                    headers={"Content-Type": "application/json"},
                )
    else:
        # RBAC: Admin has full access
        if context.role == UserRole.Admin:
            return
        # RBAC: check permission on project
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
    Authorize user access to a checklist via its project using RBAC or legacy mode.

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

        if not is_rbac_enabled():
            # Legacy: check account membership
            if account.name not in context.account_names:
                if context.role != UserRole.Admin:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Access denied",
                        headers={"Content-Type": "application/json"},
                    )
        else:
            # RBAC: Admin has full access
            if context.role == UserRole.Admin:
                return
            # RBAC: check permission on project
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
    Authorization happens here before returning the checklist.
    """
    # Get checklist from service
    checklist = await checklist_service.get_checklist(checklist_id, context, session)

    # Authorize based on checklist's project
    _authorize_checklist_access(session, checklist, context)

    return checklist


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
    Authorization happens here before delegating to checklist_service.
    """
    # Get checklist to determine project for authorization
    checklist = await checklist_service.get_checklist(checklist_id, context, session)

    # Authorize based on checklist's project (write permission for mutations)
    _authorize_checklist_access(session, checklist, context, "project.write")

    # Delegate to service for business logic
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
    Authorization happens here before delegating to checklist_service.
    """
    # Get checklist to determine project for authorization
    checklist = await checklist_service.get_checklist(checklist_id, context, session)

    # Authorize based on checklist's project (write permission for mutations)
    _authorize_checklist_access(session, checklist, context, "project.write")

    # Delegate to service for business logic
    await checklist_service.delete_checklist(checklist_id, context, session)


async def get_checklist_history(
    checklist_id: UUID,
    start_date: datetime,
    end_date: datetime,
    context: UserContext,
    session: Session,
) -> ChecklistHistoryResponse:
    """
    Get check history for a checklist within a date range.
    Authorization happens here before delegating to checklist_service.
    """
    # Get checklist to determine project for authorization
    checklist = await checklist_service.get_checklist(checklist_id, context, session)

    # Authorize based on checklist's project
    _authorize_checklist_access(session, checklist, context)

    # Delegate to service for business logic
    return await checklist_service.get_checklist_history(
        checklist_id, start_date, end_date, context, session
    )


async def get_batch_checklist_history(
    checklist_ids: list[UUID],
    start_date: datetime,
    end_date: datetime,
    context: UserContext,
    session: Session,
) -> BatchChecklistHistoryResponse:
    """
    Get check history for multiple checklists within a date range.
    Authorization happens here for each checklist before delegating to checklist_service.
    """
    # Authorize each checklist upfront
    for checklist_id in checklist_ids:
        checklist = await checklist_service.get_checklist(
            checklist_id, context, session
        )
        _authorize_checklist_access(session, checklist, context)

    # Delegate to service for business logic
    return await checklist_service.get_batch_checklist_history(
        checklist_ids, start_date, end_date, context, session
    )
