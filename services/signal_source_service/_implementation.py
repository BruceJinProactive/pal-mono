"""Signal Source Service Implementation.

Business logic for signal source CRUD operations.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.operations.signal_source import (
    CreateSignalSourceRequest,
    SignalSourceResponse,
    UpdateSignalSourceRequest,
)
from db.repositories import (
    ProjectRepositoryAsync,
    SignalFeedRepositoryAsync,
    SignalSourceRepositoryAsync,
)
from db.tables import SignalFeed, SignalSource
from db.tables.types import CaptureMode, FeedType, SignalSourceStatus, SignalType
from utils.log import logger


async def create_source(
    session: AsyncSession,
    project_id: uuid.UUID,
    request: CreateSignalSourceRequest,
) -> SignalSource:
    """
    Create a new signal source with an associated feed.

    In V1, each source has exactly one feed (1:1 relationship).
    The feed is auto-created when the source is created.

    Args:
        session: Async database session.
        project_id: Project UUID.
        request: Create request with source configuration.

    Returns:
        The created SignalSource.

    Raises:
        ValueError: If project not found.
    """
    project_repo = ProjectRepositoryAsync(session)
    source_repo = SignalSourceRepositoryAsync(session)
    feed_repo = SignalFeedRepositoryAsync(session)

    # Get project to derive account_id
    project = await project_repo.get_project(project_id)
    if not project:
        raise ValueError(f"Project {project_id} not found")

    # Validate camera_id uniqueness
    if await source_repo.camera_id_exists(project_id, request.config.camera_id):
        raise ValueError(
            f"camera_id '{request.config.camera_id}' already exists in project"
        )

    # Create the signal source
    source = SignalSource(
        account_id=project.account_id,
        project_id=project_id,
        signal_type=SignalType.camera,  # V1: Only camera supported
        name=request.name,
        description=request.description,
        status=SignalSourceStatus.active,
        config=request.config.model_dump(),
    )

    created_source = await source_repo.create(source)

    # Auto-create the associated feed (1:1 in V1)
    feed = SignalFeed(
        source_id=created_source.id,
        feed_type=FeedType.image_snapshot,  # V1: Default to image snapshot
        capture_mode=CaptureMode.pull,  # V1: Default to scheduled pull
    )

    await feed_repo.create(feed)

    logger.info(
        f"Created signal source {created_source.id} with feed for project {project_id}"
    )
    return created_source


async def get_sources(
    session: AsyncSession,
    project_id: uuid.UUID,
) -> list[SignalSource]:
    """
    Get all signal sources for a project.

    Args:
        session: Async database session.
        project_id: Project UUID.

    Returns:
        List of SignalSource objects for the project.

    Raises:
        ValueError: If project not found.
    """
    project_repo = ProjectRepositoryAsync(session)
    source_repo = SignalSourceRepositoryAsync(session)

    # Get project to derive account_id
    project = await project_repo.get_project(project_id)
    if not project:
        raise ValueError(f"Project {project_id} not found")

    return await source_repo.get_by_account(project.account_id, project_id)


async def get_source(
    session: AsyncSession,
    project_id: uuid.UUID,
    source_id: uuid.UUID,
) -> SignalSource | None:
    """
    Get a signal source by ID.

    Verifies the source belongs to the specified project.

    Args:
        session: Async database session.
        project_id: Project UUID.
        source_id: Source UUID.

    Returns:
        SignalSource if found and belongs to project, None otherwise.
    """
    project_repo = ProjectRepositoryAsync(session)
    source_repo = SignalSourceRepositoryAsync(session)

    # Get project to derive account_id
    project = await project_repo.get_project(project_id)
    if not project:
        return None

    source = await source_repo.get_by_id(source_id)

    # Verify source belongs to account and project
    if (
        source
        and source.account_id == project.account_id
        and source.project_id == project_id
    ):
        return source

    return None


async def get_source_by_camera_id(
    session: AsyncSession,
    project_id: uuid.UUID,
    camera_id: str,
) -> SignalSource | None:
    """
    Get a signal source by camera_id within a project.

    Args:
        session: Async database session.
        project_id: Project UUID.
        camera_id: Camera identifier from config.

    Returns:
        SignalSource if found, None otherwise.
    """
    source_repo = SignalSourceRepositoryAsync(session)
    return await source_repo.get_by_camera_id(project_id, camera_id)


async def update_source(
    session: AsyncSession,
    project_id: uuid.UUID,
    source_id: uuid.UUID,
    request: UpdateSignalSourceRequest,
) -> SignalSource | None:
    """
    Update a signal source.

    Cannot change signal_type or project_id.

    Args:
        session: Async database session.
        project_id: Project UUID.
        source_id: Source UUID.
        request: Update request.

    Returns:
        Updated SignalSource if found, None otherwise.
    """
    project_repo = ProjectRepositoryAsync(session)
    source_repo = SignalSourceRepositoryAsync(session)

    # Get project to derive account_id
    project = await project_repo.get_project(project_id)
    if not project:
        return None

    # Verify source exists and belongs to project
    source = await source_repo.get_by_id(source_id)
    if (
        not source
        or source.account_id != project.account_id
        or source.project_id != project_id
    ):
        return None

    # Build updates
    updates = {}
    if request.name is not None:
        updates["name"] = request.name
    if request.description is not None:
        updates["description"] = request.description
    if request.status is not None:
        updates["status"] = request.status
    if request.config is not None:
        # Validate camera_id is present and non-empty
        camera_id = request.config.camera_id
        if not camera_id or not camera_id.strip():
            raise ValueError("camera_id is required and cannot be empty")

        # Validate camera_id uniqueness if config is being updated
        if await source_repo.camera_id_exists(
            project_id, camera_id, exclude_source_id=source_id
        ):
            raise ValueError(f"camera_id '{camera_id}' already exists in project")
        updates["config"] = request.config.model_dump()

    if not updates:
        return source

    updated_source = await source_repo.update(source_id, **updates)
    logger.info(f"Updated signal source {source_id}")
    return updated_source


async def delete_source(
    session: AsyncSession,
    project_id: uuid.UUID,
    source_id: uuid.UUID,
) -> bool:
    """
    Delete a signal source and its associated feed.

    Args:
        session: Async database session.
        project_id: Project UUID.
        source_id: Source UUID.

    Returns:
        True if deleted, False if not found.
    """
    project_repo = ProjectRepositoryAsync(session)
    source_repo = SignalSourceRepositoryAsync(session)
    feed_repo = SignalFeedRepositoryAsync(session)

    # Get project to derive account_id
    project = await project_repo.get_project(project_id)
    if not project:
        return False

    # Verify source exists and belongs to project
    source = await source_repo.get_by_id(source_id)
    if (
        not source
        or source.account_id != project.account_id
        or source.project_id != project_id
    ):
        return False

    # Delete feed first (1:1 relationship in V1)
    await feed_repo.delete_by_source_id(source_id)

    # Delete source
    deleted = await source_repo.delete(source_id)
    if deleted:
        logger.info(f"Deleted signal source {source_id} and its feed")

    return deleted


def build_source_response(
    source: SignalSource,
    last_capture_at=None,
) -> SignalSourceResponse:
    """
    Build a SignalSourceResponse from a SignalSource model.

    Args:
        source: SignalSource database model.
        last_capture_at: Optional last capture timestamp from feed.

    Returns:
        SignalSourceResponse for API response.
    """
    return SignalSourceResponse(
        id=source.id,
        account_id=source.account_id,
        project_id=source.project_id,
        name=source.name,
        signal_type=source.signal_type,
        status=source.status,
        status_message=source.status_message,
        config=source.config,
        description=source.description,
        last_capture_at=last_capture_at,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


async def get_camera_stats_by_accounts(
    session: AsyncSession, account_names: list[str] | None = None
) -> dict:
    """
    Get camera statistics grouped by account.

    A camera is considered "active" if its last_capture_at timestamp is within
    the last 3 minutes (matching the admin console logic).

    Uses a single optimized database query with JOINs for best performance.

    Args:
        session: Async database session
        account_names: Optional list of account names to filter by

    Returns:
        dict: Camera statistics with the following structure:
            {
                "accounts": [
                    {
                        "account_id": str,
                        "account_name": str,
                        "total_cameras": int,
                        "active_cameras": int,
                        "has_active": bool,  # True if any camera is active
                    },
                    ...
                ],
                "total_cameras": int,
                "total_active": int,
            }
    """
    try:
        # Calculate the "active" threshold: cameras with last_capture_at within last 3 minutes
        # This matches the logic in api/routes/internal/monitoring.py
        active_threshold = datetime.now(timezone.utc) - timedelta(minutes=3)

        source_repo = SignalSourceRepositoryAsync(session)

        # Use efficient batch query for all cases
        # Note: SQLAlchemy async sessions don't support concurrent operations,
        # so a single JOIN query is both faster and more reliable than parallel queries
        if account_names:
            logger.info(
                f"[CameraStats] Querying camera statistics for {len(account_names)} account(s): {', '.join(account_names)}"
            )
        else:
            logger.info("[CameraStats] Querying camera statistics from database")

        cameras_with_feeds = await source_repo.get_cameras_with_feeds_by_account_names(
            account_names
        )

        if not cameras_with_feeds:
            if account_names:
                logger.info(
                    f"[CameraStats] No cameras found for account(s): {', '.join(account_names)}"
                )
            else:
                logger.info("[CameraStats] No cameras found in database")
            return {"accounts": [], "total_cameras": 0, "total_active": 0}

        logger.info(f"[CameraStats] Found {len(cameras_with_feeds)} total cameras")

        # Group cameras by account_id
        accounts_map = {}

        for camera, feed, account_name in cameras_with_feeds:
            account_id = str(camera.account_id)

            # Initialize account entry if not exists
            if account_id not in accounts_map:
                accounts_map[account_id] = {
                    "account_id": account_id,
                    "account_name": account_name,
                    "total_cameras": 0,
                    "active_cameras": 0,
                    "has_active": False,
                }

            # Count total cameras
            accounts_map[account_id]["total_cameras"] += 1

            # Check if camera is active based on last_capture_at
            if feed and feed.last_capture_at:
                if feed.last_capture_at >= active_threshold:
                    accounts_map[account_id]["active_cameras"] += 1
                    accounts_map[account_id]["has_active"] = True

        accounts_list = list(accounts_map.values())

        # Sort by account name
        accounts_list.sort(key=lambda x: x["account_name"] or x["account_id"])

        total_cameras = sum(a["total_cameras"] for a in accounts_list)
        total_active = sum(a["active_cameras"] for a in accounts_list)

        logger.info(
            f"[CameraStats] Summary: {len(accounts_list)} accounts, "
            f"{total_cameras} total cameras, {total_active} active"
        )

        return {
            "accounts": accounts_list,
            "total_cameras": total_cameras,
            "total_active": total_active,
        }

    except Exception as e:
        logger.error(
            f"[CameraStats] Error querying camera statistics: {e}", exc_info=True
        )
        raise
