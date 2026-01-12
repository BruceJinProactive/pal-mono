"""
Routine Service Implementation

Business logic for routine and routine item operations.
Authorization is handled in the API layer.
"""

import asyncio
import datetime
from datetime import time
from uuid import UUID

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.exc import IntegrityError
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
from utils.log import logger


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


async def _build_item_response(item: RoutineItem) -> RoutineItemResponse:
    """Build a RoutineItemResponse from database model."""
    import asyncio

    from services.asset_service import map_uri_to_s3_url

    # Ensure reference_images is always a list
    ref_images = item.reference_images
    if not isinstance(ref_images, list):
        ref_images = []

    # Convert S3 keys to presigned URLs for API response (run in thread pool)
    converted_images = []
    for img in ref_images:
        if isinstance(img, dict):
            image_url = img.get("image_url")
            # Convert S3 key to presigned URL (run in thread pool to avoid blocking)
            presigned_url = (
                await asyncio.to_thread(map_uri_to_s3_url, image_url)
                if image_url
                else ""
            )
            converted_images.append(
                {"image_url": presigned_url, "description": img.get("description", "")}
            )

    return RoutineItemResponse(
        id=item.id,
        routine_id=item.routine_id,
        name=item.name,
        description=item.description,
        sort_order=item.sort_order,
        input_type=item.input_type,
        is_required=item.is_required,
        reference_images=converted_images,  # Now contains presigned URLs
        ai_rules=item.ai_rules or {},
        signal_source_id=item.signal_source_id,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


async def _build_routine_detail_response(
    routine: Routine,
    items: list[RoutineItem],
) -> RoutineDetailResponse:
    """Build a RoutineDetailResponse from database models."""
    import asyncio

    # Build item responses concurrently
    item_responses = await asyncio.gather(
        *[_build_item_response(item) for item in items]
    )

    return RoutineDetailResponse(
        id=routine.id,
        project_id=routine.project_id,
        name=routine.name,
        description=routine.description,
        category=routine.category,
        is_active=routine.is_active,
        created_at=routine.created_at,
        updated_at=routine.updated_at,
        items=item_responses,
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
    try:
        routine = await routine_repo.create_routine(
            project_id=project_id,
            name=request.name,
            description=request.description,
            category=request.category,
        )
    except IntegrityError as e:
        if "routines_project_name_idx" in str(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A routine with the name '{request.name}' already exists for this project",
                headers={"Content-Type": "application/json"},
            ) from e
        raise

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

    # Build response before commit to avoid async I/O issues
    # (session.commit() expires objects, and accessing attributes
    # in sync _build_routine_detail_response would trigger greenlet errors)
    response = await _build_routine_detail_response(routine, items)

    await session.commit()

    return response


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

    return await _build_routine_detail_response(routine, items)


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

    # Build response before commit to avoid async I/O issues
    # (session.commit() expires objects, and accessing attributes
    # in sync _build_routine_response would trigger greenlet errors)
    response = _build_routine_response(updated)

    await session.commit()

    return response


async def delete_routine(
    routine_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> None:
    """
    Delete a routine and all associated data, including S3 reference images.
    Authorization is handled in the API layer.
    """
    from services import asset_service

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

    # Delete in order: submissions -> executions -> schedules -> S3 images -> items -> routine
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

    # Delete all reference images from S3 for all items in this routine
    items = await routine_repo.list_items_by_routine(routine_id)
    for item in items:
        reference_images = item.reference_images or []
        if isinstance(reference_images, list):
            for img in reference_images:
                if isinstance(img, dict):
                    url = img.get("image_url")
                    if url:
                        try:
                            # Extract S3 key from URL
                            if "/routines/" in url:
                                s3_key = url.split("/routines/", 1)[1]
                                s3_key = f"routines/{s3_key}"
                                asset_service.delete_asset(s3_key)
                        except Exception as e:
                            # Log error but don't fail the deletion
                            logger.warning(
                                f"Failed to delete S3 asset for URL {url} during routine deletion: {e}",
                                extra={
                                    "routine_id": str(routine_id),
                                    "item_id": str(item.id),
                                    "url": url,
                                    "error": str(e),
                                },
                            )

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

    # Build response before commit to avoid async I/O issues
    # (session.commit() expires objects, and accessing attributes
    # in sync _build_item_response would trigger greenlet errors)
    response = await _build_item_response(item)

    await session.commit()

    return response


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

    return await _build_item_response(item)


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

    # Build response before commit to avoid async I/O issues
    # (session.commit() expires objects, and accessing attributes
    # in sync _build_item_response would trigger greenlet errors)
    response = await _build_item_response(updated)

    await session.commit()

    return response


async def delete_item(
    item_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> None:
    """
    Delete a routine item and its associated reference images from S3.
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

    # Delete all reference images from S3 before deleting the item
    reference_images = item.reference_images or []
    if isinstance(reference_images, list):
        for img in reference_images:
            if isinstance(img, dict):
                url = img.get("image_url")
                if url:
                    try:
                        # Extract S3 key from URL
                        if "/routines/" in url:
                            s3_key = url.split("/routines/", 1)[1]
                            s3_key = f"routines/{s3_key}"
                            asset_service.delete_asset(s3_key)
                    except Exception as e:
                        # Log error but don't fail the deletion
                        logger.warning(
                            f"Failed to delete S3 asset for URL {url} during item deletion: {e}",
                            extra={
                                "item_id": str(item_id),
                                "url": url,
                                "error": str(e),
                            },
                        )

    # Delete the item from database
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
    description: str | None,
    context: UserContext,
    session: AsyncSession,
) -> dict[str, str]:
    """
    Upload a reference image for a routine item.
    Uses asset_service for S3 upload.
    Appends the new image to the existing list of reference images.
    Authorization is handled in the API layer.

    Args:
        item_id: UUID of the routine item
        file: The uploaded file
        description: Optional description of the reference image
        context: User context
        session: Database session

    Returns:
        Dict with 'image_url' and 'description' fields
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
    # Path: routines/{project_id}/{routine_id}/reference/{item_id}_{timestamp}_{filename}
    content = await file.read()
    filename = file.filename or "reference.jpg"
    timestamp = int(datetime.datetime.now().timestamp())

    asset_path = f"routines/{routine.project_id}/{routine.id}/reference/{item_id}_{timestamp}_{filename}"

    from api.schemas.asset.asset import WriteAssetRequest

    asset_request = WriteAssetRequest(
        name=asset_path,
        content=content,
        metadata={},
    )
    # Run sync S3 operation in thread pool to avoid blocking async event loop
    response = await asyncio.to_thread(asset_service.write_asset, asset_request)
    # Store S3 key instead of presigned URL
    s3_key = response.url

    # Append the new image to the existing list
    new_reference_image = {
        "image_url": s3_key,  # Store S3 key, not presigned URL
        "description": description or "",
    }

    # Get current reference images and append the new one
    current_images = item.reference_images
    if not isinstance(current_images, list):
        current_images = []
    updated_images = current_images + [new_reference_image]

    await routine_repo.update_routine_item(
        item_id=item_id,
        reference_images=updated_images,
    )

    await session.commit()

    # Convert S3 key to presigned URL for API response (run in thread pool)
    from services.asset_service import map_uri_to_s3_url

    presigned_url = await asyncio.to_thread(map_uri_to_s3_url, s3_key) if s3_key else ""

    return {
        "image_url": presigned_url,
        "description": description or "",
    }


async def update_reference_images(
    item_id: UUID,
    new_images: list[dict[str, str]],
    context: UserContext,
    session: AsyncSession,
) -> list[dict[str, str]]:
    """
    Update the complete list of reference images for a routine item.

    This function compares the new list with existing images:
    - Keeps images that have matching image_url (unchanged)
    - Deletes images from S3 that are no longer in the new list
    - Uploads new images that don't have an image_url yet

    Authorization is handled in the API layer.

    Args:
        item_id: UUID of the routine item
        new_images: Complete new list of reference images
                   Each dict should have 'image_url' and 'description' fields
                   Entries with empty 'image_url' are filtered out
        context: User context
        session: Database session

    Returns:
        List of dicts with 'image_url' and 'description' fields (all with S3 URLs)
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

    # Get current reference images
    current_images = item.reference_images or []
    current_urls = {
        img.get("image_url") for img in current_images if img.get("image_url")
    }
    new_urls = {img.get("image_url") for img in new_images if img.get("image_url")}

    # Determine which images to delete from S3
    urls_to_delete = current_urls - new_urls

    # Delete old images from S3
    if urls_to_delete:
        from services import asset_service

        for url in urls_to_delete:
            if url:
                try:
                    # Extract the S3 key from the URL
                    # Parse the S3 key from the URL
                    # URL format: routines/{project_id}/{routine_id}/reference/{filename}
                    if "/routines/" in url:
                        s3_key = url.split("/routines/", 1)[1]
                        s3_key = f"routines/{s3_key}"

                        # delete_asset takes a string file_name, not a request object
                        asset_service.delete_asset(s3_key)
                except Exception as e:
                    # Log error but don't fail the entire operation
                    logger.warning(
                        f"Failed to delete S3 asset for URL {url}: {e}",
                        extra={"item_id": str(item_id), "url": url, "error": str(e)},
                    )

    # Update the item with the new reference images list
    # Filter out entries with empty/missing image_url
    final_images = []
    for img in new_images:
        image_url = img.get("image_url", "").strip()
        if image_url:
            final_images.append(
                {
                    "image_url": image_url,
                    "description": img.get("description", ""),
                }
            )

    await routine_repo.update_routine_item(
        item_id=item_id,
        reference_images=final_images,
    )

    await session.commit()

    # Convert S3 keys to presigned URLs for API response (run in thread pool, parallel)
    from services.asset_service import map_uri_to_s3_url

    async def convert_image(img: dict) -> dict:
        """Convert S3 key to presigned URL in thread pool."""
        image_url = img.get("image_url")
        presigned_url = (
            await asyncio.to_thread(map_uri_to_s3_url, image_url) if image_url else ""
        )
        return {"image_url": presigned_url, "description": img.get("description", "")}

    converted_images = await asyncio.gather(
        *[convert_image(img) for img in final_images]
    )

    return converted_images
