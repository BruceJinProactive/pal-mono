"""
Routine Service Implementation

Business logic for routine and routine item operations.
Authorization is handled in the API layer.
"""

from datetime import time
from uuid import UUID

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.operations.routine import (
    CreateRoutineItemRequest,
    CreateRoutineRequest,
    ListRoutinesResponse,
    RoutineDetailResponse,
    RoutineItemResponse,
    RoutineResponse,
    UpdateRoutineItemRequest,
    UpdateRoutineRequest,
)
from db.repositories import (
    RoutineExecutionRepositoryAsync,
    RoutineRepositoryAsync,
    RoutineScheduleRepositoryAsync,
    RoutineSubmissionRepositoryAsync,
)
from db.tables.routine_items import RoutineItem
from db.tables.routines import Routine
from services.auth_types import UserContext
from services.routine_service._schedule_calculator import calculate_next_executions


def _build_routine_response(routine: Routine) -> RoutineResponse:
    """Build a RoutineResponse from database model."""
    return RoutineResponse(
        id=routine.id,
        project_id=routine.project_id,
        name=routine.name,
        description=routine.description,
        category=routine.category,
        is_active=routine.is_active,
        created_at=routine.created_at,
        updated_at=routine.updated_at,
    )


def _build_item_response(item: RoutineItem) -> RoutineItemResponse:
    """Build a RoutineItemResponse from database model."""
    return RoutineItemResponse(
        id=item.id,
        routine_id=item.routine_id,
        name=item.name,
        description=item.description,
        sort_order=item.sort_order,
        input_type=item.input_type,
        is_required=item.is_required,
        reference_image_url=item.reference_image_url,
        ai_rules=item.ai_rules or {},
        signal_source_id=item.signal_source_id,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _build_routine_detail_response(
    routine: Routine,
    items: list[RoutineItem],
) -> RoutineDetailResponse:
    """Build a RoutineDetailResponse from database models."""
    return RoutineDetailResponse(
        id=routine.id,
        project_id=routine.project_id,
        name=routine.name,
        description=routine.description,
        category=routine.category,
        is_active=routine.is_active,
        created_at=routine.created_at,
        updated_at=routine.updated_at,
        items=[_build_item_response(item) for item in items],
    )


def _parse_time(time_str: str) -> time:
    """Parse HH:MM string to time object.

    Args:
        time_str: Time string in HH:MM format

    Returns:
        time object

    Raises:
        HTTPException: If time format is invalid
    """
    try:
        parts = time_str.split(":")
        if len(parts) != 2:
            raise ValueError("Expected HH:MM format")
        hour = int(parts[0])
        minute = int(parts[1])
        return time(hour=hour, minute=minute)
    except (ValueError, IndexError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid time format '{time_str}': expected HH:MM (e.g., '09:00')",
            headers={"Content-Type": "application/json"},
        ) from e


async def create_routine(
    project_id: UUID,
    request: CreateRoutineRequest,
    context: UserContext,
    session: AsyncSession,
) -> RoutineDetailResponse:
    """
    Create a new routine with items, schedule, and initial executions.
    Authorization is handled in the API layer.
    """
    routine_repo = RoutineRepositoryAsync(session)
    schedule_repo = RoutineScheduleRepositoryAsync(session)
    execution_repo = RoutineExecutionRepositoryAsync(session)

    # Create the routine
    routine = await routine_repo.create_routine(
        project_id=project_id,
        name=request.name,
        description=request.description,
        category=request.category,
    )

    # Create items if provided
    items = []
    for idx, item_request in enumerate(request.items):
        sort_order = (
            item_request.sort_order if item_request.sort_order is not None else idx
        )
        ai_rules = item_request.ai_rules.model_dump() if item_request.ai_rules else {}

        item = await routine_repo.create_routine_item(
            routine_id=routine.id,
            name=item_request.name,
            description=item_request.description,
            sort_order=sort_order,
            input_type=item_request.input_type,
            is_required=item_request.is_required,
            ai_rules=ai_rules,
            signal_source_id=item_request.signal_source_id,
        )
        items.append(item)

    # Parse schedule times upfront to avoid accessing model attributes later
    # (accessing SQLAlchemy model attributes can trigger async I/O and cause
    # "greenlet_spawn has not been called" errors in sync contexts)
    schedule_start_time = _parse_time(request.schedule.start_time)
    schedule_end_time = _parse_time(request.schedule.end_time)

    # Create schedule (required)
    schedule = await schedule_repo.create_schedule(
        routine_id=routine.id,
        frequency=request.schedule.frequency,
        start_time=schedule_start_time,
        end_time=schedule_end_time,
        timezone=request.schedule.timezone,
        days_of_week=request.schedule.days_of_week,
        day_of_month=request.schedule.day_of_month,
        interval_hours=request.schedule.interval_hours,
        effective_from=request.schedule.effective_from,
        effective_until=request.schedule.effective_until,
    )

    # Generate next 10 executions using request values directly
    # to avoid async I/O issues with SQLAlchemy model attribute access
    execution_windows = calculate_next_executions(
        frequency=request.schedule.frequency.value,
        start_time=schedule_start_time,
        end_time=schedule_end_time,
        timezone=request.schedule.timezone,
        days_of_week=request.schedule.days_of_week,
        day_of_month=request.schedule.day_of_month,
        effective_from=request.schedule.effective_from,
        effective_until=request.schedule.effective_until,
        count=10,
    )

    for scheduled_start, scheduled_end in execution_windows:
        await execution_repo.create_execution(
            routine_id=routine.id,
            schedule_id=schedule.id,
            scheduled_start=scheduled_start,
            scheduled_end=scheduled_end,
        )

    await session.commit()

    return _build_routine_detail_response(routine, items)


async def get_routine(
    routine_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> RoutineDetailResponse:
    """
    Get a routine by ID with its items.
    Authorization is handled in the API layer.
    """
    routine_repo = RoutineRepositoryAsync(session)

    routine = await routine_repo.get_routine_by_id(routine_id)

    if not routine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Routine {routine_id} not found",
            headers={"Content-Type": "application/json"},
        )

    items = await routine_repo.list_items_by_routine(routine_id)

    return _build_routine_detail_response(routine, items)


async def list_routines(
    project_id: UUID,
    context: UserContext,
    session: AsyncSession,
    is_active: bool | None = None,
) -> ListRoutinesResponse:
    """
    List all routines for a project.
    Authorization is handled in the API layer.
    """
    routine_repo = RoutineRepositoryAsync(session)

    routines = await routine_repo.list_routines_by_project(project_id, is_active)

    return ListRoutinesResponse(
        routines=[_build_routine_response(r) for r in routines],
        total=len(routines),
    )


async def update_routine(
    routine_id: UUID,
    request: UpdateRoutineRequest,
    context: UserContext,
    session: AsyncSession,
) -> RoutineResponse:
    """
    Update a routine.
    Authorization is handled in the API layer.
    """
    routine_repo = RoutineRepositoryAsync(session)

    routine = await routine_repo.get_routine_by_id(routine_id)

    if not routine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Routine {routine_id} not found",
            headers={"Content-Type": "application/json"},
        )

    updated = await routine_repo.update_routine(
        routine_id=routine_id,
        name=request.name,
        description=request.description,
        category=request.category,
        is_active=request.is_active,
    )

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update routine {routine_id}",
            headers={"Content-Type": "application/json"},
        )

    await session.commit()

    return _build_routine_response(updated)


async def delete_routine(
    routine_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> None:
    """
    Delete a routine and all associated data.
    Authorization is handled in the API layer.
    """
    routine_repo = RoutineRepositoryAsync(session)
    schedule_repo = RoutineScheduleRepositoryAsync(session)
    execution_repo = RoutineExecutionRepositoryAsync(session)
    submission_repo = RoutineSubmissionRepositoryAsync(session)

    routine = await routine_repo.get_routine_by_id(routine_id)

    if not routine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Routine {routine_id} not found",
            headers={"Content-Type": "application/json"},
        )

    # Delete in order: submissions -> executions -> schedules -> routine
    # (no FK constraints, so manual cascade)

    # Get execution IDs for this routine
    executions = await execution_repo.list_executions_by_routine(routine_id)
    execution_ids = [e.id for e in executions]

    # Delete submissions and their item responses
    if execution_ids:
        await submission_repo.delete_submissions_by_execution_ids(execution_ids)

    # Delete executions
    await execution_repo.delete_executions_by_routine(routine_id)

    # Delete schedules
    await schedule_repo.delete_schedules_by_routine(routine_id)

    # Delete the routine (this also deletes items via repository)
    deleted = await routine_repo.delete_routine(routine_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete routine {routine_id}",
            headers={"Content-Type": "application/json"},
        )

    await session.commit()


async def add_item(
    routine_id: UUID,
    request: CreateRoutineItemRequest,
    context: UserContext,
    session: AsyncSession,
) -> RoutineItemResponse:
    """
    Add an item to a routine.
    Authorization is handled in the API layer.
    """
    routine_repo = RoutineRepositoryAsync(session)

    routine = await routine_repo.get_routine_by_id(routine_id)

    if not routine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Routine {routine_id} not found",
            headers={"Content-Type": "application/json"},
        )

    # Auto-assign sort order if not provided
    sort_order = request.sort_order
    if sort_order is None:
        sort_order = await routine_repo.get_next_sort_order(routine_id)

    ai_rules = request.ai_rules.model_dump() if request.ai_rules else {}

    item = await routine_repo.create_routine_item(
        routine_id=routine_id,
        name=request.name,
        description=request.description,
        sort_order=sort_order,
        input_type=request.input_type,
        is_required=request.is_required,
        ai_rules=ai_rules,
        signal_source_id=request.signal_source_id,
    )

    await session.commit()

    return _build_item_response(item)


async def get_item(
    item_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> RoutineItemResponse:
    """
    Get a routine item by ID.
    Authorization is handled in the API layer.
    """
    routine_repo = RoutineRepositoryAsync(session)

    item = await routine_repo.get_routine_item_by_id(item_id)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Routine item {item_id} not found",
            headers={"Content-Type": "application/json"},
        )

    return _build_item_response(item)


async def update_item(
    item_id: UUID,
    request: UpdateRoutineItemRequest,
    context: UserContext,
    session: AsyncSession,
) -> RoutineItemResponse:
    """
    Update a routine item.
    Authorization is handled in the API layer.
    """
    routine_repo = RoutineRepositoryAsync(session)

    item = await routine_repo.get_routine_item_by_id(item_id)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Routine item {item_id} not found",
            headers={"Content-Type": "application/json"},
        )

    ai_rules = None
    if request.ai_rules is not None:
        ai_rules = request.ai_rules.model_dump()

    updated = await routine_repo.update_routine_item(
        item_id=item_id,
        name=request.name,
        description=request.description,
        sort_order=request.sort_order,
        input_type=request.input_type,
        is_required=request.is_required,
        ai_rules=ai_rules,
        signal_source_id=request.signal_source_id,
    )

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update routine item {item_id}",
            headers={"Content-Type": "application/json"},
        )

    await session.commit()

    return _build_item_response(updated)


async def delete_item(
    item_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> None:
    """
    Delete a routine item.
    Authorization is handled in the API layer.
    """
    routine_repo = RoutineRepositoryAsync(session)

    item = await routine_repo.get_routine_item_by_id(item_id)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Routine item {item_id} not found",
            headers={"Content-Type": "application/json"},
        )

    deleted = await routine_repo.delete_routine_item(item_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete routine item {item_id}",
            headers={"Content-Type": "application/json"},
        )

    await session.commit()


async def upload_reference_image(
    item_id: UUID,
    file: UploadFile,
    context: UserContext,
    session: AsyncSession,
) -> str:
    """
    Upload a reference image for a routine item.
    Uses asset_service for S3 upload.
    Authorization is handled in the API layer.
    """
    from services import asset_service

    routine_repo = RoutineRepositoryAsync(session)

    item = await routine_repo.get_routine_item_by_id(item_id)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Routine item {item_id} not found",
            headers={"Content-Type": "application/json"},
        )

    # Get the routine to get project_id for asset path
    routine = await routine_repo.get_routine_by_id(item.routine_id)

    if not routine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Routine {item.routine_id} not found",
            headers={"Content-Type": "application/json"},
        )

    # Upload to S3 via asset_service
    # Path: routines/{project_id}/{routine_id}/reference/{item_id}_{filename}
    content = await file.read()
    filename = file.filename or "reference.jpg"

    asset_path = (
        f"routines/{routine.project_id}/{routine.id}/reference/{item_id}_{filename}"
    )

    from api.schemas.asset.asset import WriteAssetRequest

    asset_request = WriteAssetRequest(
        name=asset_path,
        content=content,
        metadata={},
    )
    response = asset_service.write_asset(asset_request)
    s3_url = response.url

    # Update the item with the reference image URL
    await routine_repo.update_routine_item(
        item_id=item_id,
        reference_image_url=s3_url,
    )

    await session.commit()

    return s3_url
