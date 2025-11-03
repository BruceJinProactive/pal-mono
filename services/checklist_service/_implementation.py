"""
Checklist Service Implementation

Business logic for checklist operations including authorization,
validation, and database operations.
"""

from datetime import datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from api.routes.admin._auth import authorize_user_account
from api.routes.admin._utils import UserContext
from api.schemas.admin.checklist import (
    Checklist,
    CreateChecklistRequest,
    ListChecklistsResponse,
    UpdateChecklistRequest,
)
from db.repositories import checklist_repository
from services import account_service, project_service


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


async def get_checklist_history(
    checklist_id: UUID,
    start_date: datetime,
    end_date: datetime,
    context: UserContext,
    session: Session,
):
    """
    Get check history for a checklist within a date range.

    Returns the last run for each CURRENTLY ACTIVE checkpoint in the checklist
    within the specified date range. Checkpoints that are no longer in the
    checklist are excluded.

    Args:
        checklist_id: UUID of the checklist
        start_date: Start of date range (datetime with timezone)
        end_date: End of date range (datetime with timezone)
        context: User authentication context
        session: Database session

    Returns:
        ChecklistHistoryResponse with checkpoint history and summary
    """
    from api.routes.utils import map_uri_to_s3_url
    from api.schemas.admin.checklist import (
        ChecklistHistoryResponse,
        ChecklistHistorySummary,
        CheckpointHistoryItem,
        CheckpointRunDetail,
    )
    from services import checkpoint_service

    # Get the checklist and authorize
    checklist_db = checklist_repository.get_checklist_by_id(session, checklist_id)

    if not checklist_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Checklist {checklist_id} does not exist.",
        )

    # Authorize via checklist → project → account
    if checklist_db.project_id:
        _authorize_project_access(session, checklist_db.project_id, context)

    # Get CURRENT checkpoints in the checklist (what's in the checklist NOW)
    current_checkpoints = checkpoint_service.list_checkpoints_by_checklist(
        session, checklist_id
    )

    # Build response for each current checkpoint
    checkpoint_items = []
    with_runs = 0
    missing_runs = 0
    reviewed_runs = 0
    unreviewed_runs = 0

    for checkpoint in current_checkpoints:
        # Get the latest run for this checkpoint in the date range
        latest_run = checkpoint_service.get_latest_checkpoint_result_by_date_range(
            session=session,
            checkpoint_id=checkpoint.id,
            start_date=start_date,
            end_date=end_date,
        )

        # Build the run detail if exists
        last_run_detail = None
        if latest_run:
            with_runs += 1

            # Count review status
            if latest_run.is_reviewed:
                reviewed_runs += 1
            else:
                unreviewed_runs += 1

            # Extract image URL from result JSON if available
            image_url = (
                latest_run.result.get("image_url") if latest_run.result else None
            )
            # Convert S3 path to presigned URL if exists
            presigned_url = map_uri_to_s3_url(image_url) if image_url else None

            last_run_detail = CheckpointRunDetail(
                run_id=str(latest_run.id),
                status=(
                    latest_run.result.get("status", "unknown")
                    if latest_run.result
                    else "unknown"
                ),
                result=latest_run.result or {},
                created_at=latest_run.created_at.isoformat(),
                image_url=presigned_url,
                review=latest_run.review,
                reviewer=latest_run.reviewer,
                is_reviewed=latest_run.is_reviewed,
            )
        else:
            missing_runs += 1

        checkpoint_items.append(
            CheckpointHistoryItem(
                checkpoint_id=str(checkpoint.id),
                checkpoint_name=checkpoint.name,
                last_run=last_run_detail,
            )
        )

    # Build summary
    summary = ChecklistHistorySummary(
        total_checkpoints=len(current_checkpoints),
        with_runs=with_runs,
        missing_runs=missing_runs,
        reviewed_runs=reviewed_runs,
        unreviewed_runs=unreviewed_runs,
    )

    return ChecklistHistoryResponse(
        checklist_id=str(checklist_id),
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        checkpoints=checkpoint_items,
        summary=summary,
    )


async def get_batch_checklist_history(
    checklist_ids: list[UUID],
    start_date: datetime,
    end_date: datetime,
    context: UserContext,
    session: Session,
):
    """
    Get check history for multiple checklists within a date range.

    Args:
        checklist_ids: List of checklist UUIDs
        start_date: Start of date range (datetime with timezone)
        end_date: End of date range (datetime with timezone)
        context: User authentication context
        session: Database session

    Returns:
        BatchChecklistHistoryResponse with list of checklist history responses
    """
    from api.schemas.admin.checklist import BatchChecklistHistoryResponse

    results = []
    for checklist_id in checklist_ids:
        result = await get_checklist_history(
            checklist_id, start_date, end_date, context, session
        )
        results.append(result)

    return BatchChecklistHistoryResponse(results=results)
