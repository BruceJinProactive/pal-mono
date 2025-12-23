"""Signal Sources API Routes Implementation.

Business logic handlers for signal source CRUD endpoints.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.operations.signal_source import (
    CreateSignalSourceRequest,
    ListSignalSourcesResponse,
    SignalSourceResponse,
    UpdateSignalSourceRequest,
)
from db.repositories import SignalFeedRepositoryAsync
from services import signal_source_service
from utils.log import logger


async def create_signal_source(
    request: CreateSignalSourceRequest,
    session: AsyncSession,
    project_id: uuid.UUID,
) -> SignalSourceResponse:
    """
    Create a new signal source.

    Args:
        request: Create request with source configuration.
        session: Async database session.
        project_id: Project UUID from path.

    Returns:
        Created SignalSourceResponse.

    Raises:
        HTTPException: If creation fails.
    """
    try:
        source = await signal_source_service.create_source(
            session=session,
            project_id=project_id,
            request=request,
        )

        await session.commit()

        return signal_source_service.build_source_response(source)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except Exception as e:
        logger.error(f"Error creating signal source: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create signal source",
            headers={"Content-Type": "application/json"},
        )


async def list_signal_sources(
    session: AsyncSession,
    project_id: uuid.UUID,
    page: int = 1,
    page_size: int = 20,
) -> ListSignalSourcesResponse:
    """
    List signal sources for a project.

    Args:
        session: Async database session.
        project_id: Project UUID from path.
        page: Page number (1-based).
        page_size: Items per page.

    Returns:
        ListSignalSourcesResponse with paginated results.
    """
    try:
        sources = await signal_source_service.get_sources(
            session=session,
            project_id=project_id,
        )

        feed_repo = SignalFeedRepositoryAsync(session)

        # Build responses with last_capture_at from feeds
        items = []
        for source in sources:
            feed = await feed_repo.get_by_source_id(source.id)
            last_capture_at = feed.last_capture_at if feed else None
            items.append(
                signal_source_service.build_source_response(source, last_capture_at)
            )

        # Apply pagination
        total = len(items)
        start = (page - 1) * page_size
        end = start + page_size
        paginated_items = items[start:end]

        return ListSignalSourcesResponse(
            items=paginated_items,
            total=total,
            page=page,
            page_size=page_size,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except Exception as e:
        logger.error(f"Error listing signal sources: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list signal sources",
            headers={"Content-Type": "application/json"},
        )


async def get_signal_source(
    source_id: uuid.UUID,
    session: AsyncSession,
    project_id: uuid.UUID,
) -> SignalSourceResponse:
    """
    Get a signal source by ID.

    Args:
        source_id: Source UUID.
        session: Async database session.
        project_id: Project UUID from path.

    Returns:
        SignalSourceResponse.

    Raises:
        HTTPException: If source not found.
    """
    source = await signal_source_service.get_source(
        session=session,
        project_id=project_id,
        source_id=source_id,
    )

    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Signal source {source_id} not found",
            headers={"Content-Type": "application/json"},
        )

    feed_repo = SignalFeedRepositoryAsync(session)
    feed = await feed_repo.get_by_source_id(source.id)
    last_capture_at = feed.last_capture_at if feed else None

    return signal_source_service.build_source_response(source, last_capture_at)


async def update_signal_source(
    source_id: uuid.UUID,
    request: UpdateSignalSourceRequest,
    session: AsyncSession,
    project_id: uuid.UUID,
) -> SignalSourceResponse:
    """
    Update a signal source.

    Args:
        source_id: Source UUID.
        request: Update request.
        session: Async database session.
        project_id: Project UUID from path.

    Returns:
        Updated SignalSourceResponse.

    Raises:
        HTTPException: If source not found or update fails.
    """
    try:
        updated_source = await signal_source_service.update_source(
            session=session,
            project_id=project_id,
            source_id=source_id,
            request=request,
        )

        if not updated_source:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Signal source {source_id} not found",
                headers={"Content-Type": "application/json"},
            )

        await session.commit()

        feed_repo = SignalFeedRepositoryAsync(session)
        feed = await feed_repo.get_by_source_id(updated_source.id)
        last_capture_at = feed.last_capture_at if feed else None

        return signal_source_service.build_source_response(
            updated_source, last_capture_at
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except Exception as e:
        logger.error(f"Error updating signal source: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update signal source",
            headers={"Content-Type": "application/json"},
        )


async def delete_signal_source(
    source_id: uuid.UUID,
    session: AsyncSession,
    project_id: uuid.UUID,
) -> None:
    """
    Delete a signal source and its associated feed.

    Args:
        source_id: Source UUID.
        session: Async database session.
        project_id: Project UUID from path.

    Raises:
        HTTPException: If source not found.
    """
    deleted = await signal_source_service.delete_source(
        session=session,
        project_id=project_id,
        source_id=source_id,
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Signal source {source_id} not found",
            headers={"Content-Type": "application/json"},
        )

    await session.commit()
