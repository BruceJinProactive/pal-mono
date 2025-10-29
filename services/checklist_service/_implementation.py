"""
Checklist Service Implementation

Business logic for checklist operations including authorization,
validation, and database operations.
"""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from api.routes.admin._auth import authorize_user_account
from api.routes.admin._utils import UserContext
from api.schemas.admin.checklist import (
    Checklist,
    ChecklistCheckpointStatusResponse,
    ChecklistCheckpointStatusSummary,
    CheckpointLastRunSummary,
    CheckpointStatusItem,
    CreateChecklistRequest,
    ListChecklistsResponse,
    UpdateChecklistRequest,
)
from db.repositories import checklist_repository, checkpoint_repository
from services import account_service, checkpoint_service, project_service


def _build_checklist(checklist_db) -> Checklist:
    """
    Build a Checklist response from database model.

    Args:
        checklist_db: Database checklist object

    Returns:
        Checklist schema object
    """
    return Checklist(
        id=str(checklist_db.id),
        project_id=str(checklist_db.project_id) if checklist_db.project_id else None,
        name=checklist_db.name,
        description=checklist_db.description,
        ai_enabled=checklist_db.ai_enabled,
        created_at=checklist_db.created_at,
        updated_at=checklist_db.updated_at,
    )


def _authorize_project_access(
    session: Session,
    project_id: UUID,
    context: UserContext,
):
    """
    Validate project exists and authorize user access.

    Args:
        session: Database session
        project_id: Project UUID
        context: User context

    Raises:
        HTTPException: If project not found or authorization fails
    """
    project = project_service.get_project(session, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} does not exist.",
        )

    account = account_service.get_account_by_id(session, project.account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account for project {project_id} does not exist.",
        )

    authorize_user_account(context, account.name)


async def create_checklist(
    project_id: UUID,
    checklist_request: CreateChecklistRequest,
    context: UserContext,
    session: Session,
) -> Checklist:
    """
    Create a new checklist with authorization and validation.

    Args:
        project_id: UUID of the project
        checklist_request: Request containing checklist data
        context: User authentication context
        session: Database session

    Returns:
        Created Checklist object
    """
    # Authorize project access
    _authorize_project_access(session, project_id, context)

    # Create the checklist with the project_id from the URL
    checklist_db = checklist_repository.create_checklist(
        session=session,
        name=checklist_request.name,
        project_id=project_id,
        description=checklist_request.description,
        ai_enabled=checklist_request.ai_enabled,
    )

    session.commit()

    return _build_checklist(checklist_db)


async def get_checklist(
    checklist_id: UUID,
    context: UserContext,
    session: Session,
) -> Checklist:
    """
    Get a checklist by ID with authorization.

    Args:
        checklist_id: UUID of the checklist
        context: User authentication context
        session: Database session

    Returns:
        Checklist object
    """
    checklist_db = checklist_repository.get_checklist_by_id(session, checklist_id)

    if not checklist_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Checklist {checklist_id} does not exist.",
        )

    # If checklist is associated with a project, verify user has access
    if checklist_db.project_id:
        project = project_service.get_project(session, checklist_db.project_id)
        if project:
            account = account_service.get_account_by_id(session, project.account_id)
            if account:
                authorize_user_account(context, account.name)

    return _build_checklist(checklist_db)


async def list_checklists_by_project(
    project_id: UUID,
    context: UserContext,
    session: Session,
    exclude: UUID | None = None,
) -> ListChecklistsResponse:
    """
    List all checklists for a project with authorization.

    Args:
        project_id: UUID of the project
        context: User authentication context
        session: Database session
        exclude: Optional checklist ID to exclude from results

    Returns:
        ListChecklistsResponse with checklists and total count
    """
    # Authorize project access
    _authorize_project_access(session, project_id, context)

    # Get checklists for the project
    checklists_db = checklist_repository.list_checklists_by_project(
        session, project_id, exclude
    )

    return ListChecklistsResponse(
        checklists=[_build_checklist(c) for c in checklists_db],
        total=len(checklists_db),
    )


async def update_checklist(
    checklist_id: UUID,
    update_request: UpdateChecklistRequest,
    context: UserContext,
    session: Session,
) -> Checklist:
    """
    Update a checklist with authorization.

    Args:
        checklist_id: UUID of the checklist
        update_request: Request containing update data
        context: User authentication context
        session: Database session

    Returns:
        Updated Checklist object
    """
    # Get the existing checklist
    checklist_db = checklist_repository.get_checklist_by_id(session, checklist_id)

    if not checklist_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Checklist {checklist_id} does not exist.",
        )

    # If checklist is associated with a project, verify user has access
    if checklist_db.project_id:
        _authorize_project_access(session, checklist_db.project_id, context)

    # Update the checklist
    updated_checklist = checklist_repository.update_checklist(
        session=session,
        checklist_id=checklist_id,
        name=update_request.name,
        description=update_request.description,
        ai_enabled=update_request.ai_enabled,
    )

    if not updated_checklist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Failed to update checklist {checklist_id}.",
        )

    session.commit()

    return _build_checklist(updated_checklist)


async def delete_checklist(
    checklist_id: UUID,
    context: UserContext,
    session: Session,
) -> None:
    """
    Delete a checklist with authorization.

    Args:
        checklist_id: UUID of the checklist
        context: User authentication context
        session: Database session
    """
    # Get the existing checklist
    checklist_db = checklist_repository.get_checklist_by_id(session, checklist_id)

    if not checklist_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Checklist {checklist_id} does not exist.",
        )

    # If checklist is associated with a project, verify user has access
    if checklist_db.project_id:
        _authorize_project_access(session, checklist_db.project_id, context)

    # Delete the checklist
    deleted = checklist_repository.delete_checklist(session, checklist_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Failed to delete checklist {checklist_id}.",
        )

    session.commit()


async def get_checklist_checkpoint_status_by_timestamp_range(
    checklist_id: UUID,
    start_time: str,
    end_time: str,
    context: UserContext,
    session: Session,
) -> ChecklistCheckpointStatusResponse:
    """
    Get the status of all active checkpoints in a checklist within a specific time range.

    This provides a historically accurate view - only shows checkpoints that:
    1. Were active (is_active=true) at the end of the time range
    2. Were created on or before the end_time

    Handles timezone-aware timestamps from clients in different timezones.

    Args:
        checklist_id: UUID of the checklist
        start_time: ISO 8601 timestamp with timezone (e.g., "2025-09-17T00:00:00-07:00")
        end_time: ISO 8601 timestamp with timezone (e.g., "2025-09-17T23:59:59.999999-07:00")
        context: User authentication context
        session: Database session

    Returns:
        ChecklistCheckpointStatusResponse with checkpoints and their last run status

    Raises:
        HTTPException: If checklist not found or authorization fails
        TimestampValidationError: If timestamp format is invalid or missing timezone
    """
    from services.checkpoint_service._utils import (
        TimestampValidationError,
        parse_and_validate_timestamp,
    )

    # Parse and validate timestamps
    start_dt = parse_and_validate_timestamp(start_time)
    end_dt = parse_and_validate_timestamp(end_time)

    # Validate that start is before end
    if start_dt >= end_dt:
        raise TimestampValidationError(
            f"start_time ({start_time}) must be before end_time ({end_time})"
        )

    # Get checklist and validate exists
    checklist_db = checklist_repository.get_checklist_by_id(session, checklist_id)

    if not checklist_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Checklist {checklist_id} does not exist.",
        )

    # If checklist is associated with a project, authorize user access
    if checklist_db.project_id:
        _authorize_project_access(session, checklist_db.project_id, context)

    # Get all active checkpoints for this checklist that existed on or before the end timestamp
    checkpoints = (
        checkpoint_repository.list_active_checkpoints_by_checklist_before_date(
            session=session,
            checklist_id=checklist_id,
            end_date=end_dt,
        )
    )

    # Build checkpoint status items
    checkpoint_status_items = []
    checkpoints_with_runs = 0
    checkpoints_missing_runs = 0

    for checkpoint in checkpoints:
        # Get the latest checkpoint run within the time range
        last_run = checkpoint_service.get_latest_checkpoint_result_by_date_range(
            session=session,
            checkpoint_id=checkpoint.id,
            start_date=start_dt,
            end_date=end_dt,
        )

        if last_run:
            # Checkpoint has a run within the time range
            checkpoints_with_runs += 1
            last_run_summary = CheckpointLastRunSummary(
                status=last_run.status.value,
                result=last_run.result,
                created_at=(
                    last_run.created_at.isoformat() if last_run.created_at else None
                ),
                updated_at=(
                    last_run.updated_at.isoformat() if last_run.updated_at else None
                ),
            )
        else:
            # Checkpoint has no run within the time range
            checkpoints_missing_runs += 1
            last_run_summary = CheckpointLastRunSummary(
                status="missing",
                result=None,
                created_at=None,
                updated_at=None,
            )

        checkpoint_status_items.append(
            CheckpointStatusItem(
                checkpoint_id=str(checkpoint.id),
                last_run=last_run_summary,
            )
        )

    # Build summary stats
    summary = ChecklistCheckpointStatusSummary(
        total_checkpoints=len(checkpoints),
        with_runs=checkpoints_with_runs,
        missing_runs=checkpoints_missing_runs,
    )

    # Build and return response
    return ChecklistCheckpointStatusResponse(
        checklist_id=str(checklist_id),
        start_time=start_time,
        end_time=end_time,
        checkpoints=checkpoint_status_items,
        summary=summary,
    )
