"""Signal Sources API Routes Implementation.

Business logic handlers for signal source CRUD endpoints.
"""

from __future__ import annotations

import asyncio
import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.operations.signal_source import (
    CreateSignalSourceRequest,
    ListSignalSourcesResponse,
    SignalSourceIdResponse,
    SignalSourceResponse,
    UpdateSignalSourceRequest,
)
from db.repositories import SignalFeedRepositoryAsync
from services import signal_source_service
from services.asset_service import _utils as asset_utils
from utils.log import logger


async def _generate_presigned_url_safe(s3_key: str) -> str | None:
    """
    Generate presigned URL for an S3 key in a thread-safe manner.

    Runs synchronous boto3 operations in a thread pool to avoid greenlet issues
    with async SQLAlchemy sessions.

    Args:
        s3_key: S3 object key (path within bucket)

    Returns:
        Presigned URL string, or None if generation fails
    """
    try:

        def _generate():
            s3_client = asset_utils.init_s3(asset_utils.AWS_REGION)
            return asset_utils.generate_presigned_url(
                s3_client,
                asset_utils.AWS_ASSET_BUCKET_NAME,
                s3_key,
            )

        return await asyncio.to_thread(_generate)
    except Exception as e:
        logger.warning(f"Failed to generate presigned URL for {s3_key}: {e}")
        return None


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
        await session.refresh(source)

        return signal_source_service.build_source_response(
            source, last_capture_at=None, last_capture_url=None
        )

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

        # Build responses with last_capture_at and last_capture_url from feeds
        items = []
        for source in sources:
            feed = await feed_repo.get_by_source_id(source.id)
            last_capture_at = feed.last_capture_at if feed else None
            last_capture_url = None

            # Generate presigned URL if S3 key exists
            if feed and feed.last_capture_url:
                last_capture_url = await _generate_presigned_url_safe(
                    feed.last_capture_url
                )

            items.append(
                signal_source_service.build_source_response(
                    source, last_capture_at, last_capture_url
                )
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
    last_capture_url = None

    # Generate presigned URL if S3 key exists
    if feed and feed.last_capture_url:
        last_capture_url = await _generate_presigned_url_safe(feed.last_capture_url)

    return signal_source_service.build_source_response(
        source, last_capture_at, last_capture_url
    )


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
        await session.refresh(updated_source)

        feed_repo = SignalFeedRepositoryAsync(session)
        feed = await feed_repo.get_by_source_id(updated_source.id)
        last_capture_at = feed.last_capture_at if feed else None
        last_capture_url = None

        # Generate presigned URL if S3 key exists
        if feed and feed.last_capture_url:
            last_capture_url = await _generate_presigned_url_safe(feed.last_capture_url)

        return signal_source_service.build_source_response(
            updated_source, last_capture_at, last_capture_url
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


async def get_signal_source_by_camera_id(
    project_id: uuid.UUID,
    camera_id: str,
    session: AsyncSession,
) -> SignalSourceIdResponse:
    """
    Get signal source ID by camera_id.

    Args:
        project_id: Project UUID from path.
        camera_id: Camera identifier from query.
        session: Async database session.

    Returns:
        SignalSourceIdResponse with signal_source_id.

    Raises:
        HTTPException: If signal source not found.
    """
    source = await signal_source_service.get_source_by_camera_id(
        session=session,
        project_id=project_id,
        camera_id=camera_id,
    )

    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Signal source with camera_id '{camera_id}' not found in project {project_id}",
            headers={"Content-Type": "application/json"},
        )

    return SignalSourceIdResponse(signal_source_id=source.id)
