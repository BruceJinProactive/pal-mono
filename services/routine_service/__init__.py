"""
Routine Service

This service contains business logic for routine and routine item operations.
It handles validation and orchestrates database operations.
Authorization is handled in the API layer.
"""

from uuid import UUID

from fastapi import UploadFile
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
from services.auth_types import UserContext

from . import _implementation

__all__ = [
    "create_routine",
    "get_routine",
    "list_routines",
    "update_routine",
    "delete_routine",
    "add_item",
    "get_item",
    "update_item",
    "delete_item",
    "upload_reference_image",
]


async def create_routine(
    project_id: UUID,
    request: CreateRoutineRequest,
    context: UserContext,
    session: AsyncSession,
) -> RoutineDetailResponse:
    """
    Create a new routine with optional items and schedule.

    Args:
        project_id: UUID of the project
        request: Request containing routine data
        context: User authentication context
        session: Database session

    Returns:
        Created RoutineDetailResponse object
    """
    return await _implementation.create_routine(project_id, request, context, session)


async def get_routine(
    routine_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> RoutineDetailResponse:
    """
    Get a routine by ID with its items.

    Args:
        routine_id: UUID of the routine
        context: User authentication context
        session: Database session

    Returns:
        RoutineDetailResponse object
    """
    return await _implementation.get_routine(routine_id, context, session)


async def list_routines(
    project_id: UUID,
    context: UserContext,
    session: AsyncSession,
    is_active: bool | None = None,
) -> ListRoutinesResponse:
    """
    List all routines for a project.

    Args:
        project_id: UUID of the project
        context: User authentication context
        session: Database session
        is_active: Optional filter for active status

    Returns:
        ListRoutinesResponse with routines and total count
    """
    return await _implementation.list_routines(project_id, context, session, is_active)


async def update_routine(
    routine_id: UUID,
    request: UpdateRoutineRequest,
    context: UserContext,
    session: AsyncSession,
) -> RoutineResponse:
    """
    Update a routine.

    Args:
        routine_id: UUID of the routine
        request: Request containing update data
        context: User authentication context
        session: Database session

    Returns:
        Updated RoutineResponse object
    """
    return await _implementation.update_routine(routine_id, request, context, session)


async def delete_routine(
    routine_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> None:
    """
    Delete a routine and all associated items, schedules, executions, submissions.

    Args:
        routine_id: UUID of the routine
        context: User authentication context
        session: Database session
    """
    await _implementation.delete_routine(routine_id, context, session)


async def add_item(
    routine_id: UUID,
    request: CreateRoutineItemRequest,
    context: UserContext,
    session: AsyncSession,
) -> RoutineItemResponse:
    """
    Add an item to a routine.

    Args:
        routine_id: UUID of the routine
        request: Request containing item data
        context: User authentication context
        session: Database session

    Returns:
        Created RoutineItemResponse object
    """
    return await _implementation.add_item(routine_id, request, context, session)


async def get_item(
    item_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> RoutineItemResponse:
    """
    Get a routine item by ID.

    Args:
        item_id: UUID of the item
        context: User authentication context
        session: Database session

    Returns:
        RoutineItemResponse object
    """
    return await _implementation.get_item(item_id, context, session)


async def update_item(
    item_id: UUID,
    request: UpdateRoutineItemRequest,
    context: UserContext,
    session: AsyncSession,
) -> RoutineItemResponse:
    """
    Update a routine item.

    Args:
        item_id: UUID of the item
        request: Request containing update data
        context: User authentication context
        session: Database session

    Returns:
        Updated RoutineItemResponse object
    """
    return await _implementation.update_item(item_id, request, context, session)


async def delete_item(
    item_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> None:
    """
    Delete a routine item.

    Args:
        item_id: UUID of the item
        context: User authentication context
        session: Database session
    """
    await _implementation.delete_item(item_id, context, session)


async def upload_reference_image(
    item_id: UUID,
    file: UploadFile,
    context: UserContext,
    session: AsyncSession,
) -> str:
    """
    Upload a reference image for a routine item.

    Args:
        item_id: UUID of the item
        file: Uploaded file
        context: User authentication context
        session: Database session

    Returns:
        S3 URL of the uploaded image
    """
    return await _implementation.upload_reference_image(item_id, file, context, session)
