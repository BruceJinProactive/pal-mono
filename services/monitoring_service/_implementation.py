"""Monitoring Service Implementation.

Business logic for monitoring configuration and run CRUD operations.
"""

from __future__ import annotations

import asyncio
import copy
import os
import uuid
from datetime import datetime

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.operations.monitoring import (
    CreateMonitoringConfigRequest,
    MonitoringConfigResponse,
    MonitoringRunResponse,
    UpdateMonitoringConfigRequest,
)
from db.repositories import (
    MonitoringConfigRepositoryAsync,
    MonitoringRunRepositoryAsync,
    ProjectRepositoryAsync,
    SignalSourceRepositoryAsync,
)
from db.tables import MonitoringConfig, MonitoringRun
from services.asset_service import delete_asset, write_asset
from services.asset_service._implementation import WriteAssetRequest
from services.asset_service._utils import map_uri_to_s3_url
from utils.log import logger


async def upload_reference_images(
    images: list[UploadFile],
    descriptions: list[str],
    project_id: uuid.UUID,
    config_id: uuid.UUID,
) -> list[dict]:
    """
    Upload multiple reference images with descriptions to S3.

    Args:
        images: List of uploaded image files
        descriptions: List of descriptions for each image
        project_id: Project UUID
        config_id: Monitoring config UUID

    Returns:
        list[dict]: List of {"url": str, "description": str} objects

    Raises:
        HTTPException: If image upload fails
    """
    uploaded_images = []

    for idx, (image, description) in enumerate(zip(images, descriptions)):
        try:
            logger.info(
                f"Uploading reference image {idx + 1}/{len(images)}: {image.filename}"
            )

            if not image.filename:
                raise ValueError(f"Image {idx + 1} filename is required.")

            # Validate description length
            if not description or len(description) < 1 or len(description) > 500:
                raise ValueError(
                    f"Image {idx + 1} description must be between 1 and 500 characters"
                )

            # Read image content
            content = await image.read()

            # Get file extension
            file_extension = os.path.splitext(image.filename)[1] or ".jpg"

            # Generate UUID for unique filename
            image_uuid = uuid.uuid4()

            # Create S3 path with UUID (not sequential index!)
            # Format: monitoring/reference_images/{project_id}/{config_id}/{uuid}{extension}
            # Use forward slashes for S3 compatibility (not os.path.join which uses backslashes on Windows)
            file_path = f"monitoring/reference_images/{project_id}/{config_id}/{image_uuid}{file_extension}"

            # Upload to S3 with metadata
            write_asset_req = WriteAssetRequest(
                name=file_path,
                content=content,
                metadata={
                    "project_id": str(project_id),
                    "config_id": str(config_id),
                    "image_uuid": str(image_uuid),
                    "description": description,
                },
            )

            # Run blocking S3 upload in thread pool to avoid blocking async event loop
            asset_response = await asyncio.to_thread(write_asset, write_asset_req)
            logger.info(
                f"Reference image {idx + 1} uploaded successfully: {asset_response.url}"
            )

            # Return structured data
            uploaded_images.append({"url": file_path, "description": description})

        except ValueError as ve:
            logger.error(f"Validation error uploading reference image {idx + 1}: {ve}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(ve),
            )
        except Exception as e:
            logger.error(f"Error uploading reference image {idx + 1}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload reference image {idx + 1}: {str(e)}",
            )

    return uploaded_images


async def cleanup_reference_images(file_paths: list[str]) -> None:
    """
    Clean up reference images from S3 (rollback uploaded files on transaction failure).

    Args:
        file_paths: List of S3 file paths to delete

    Note:
        This function logs errors but does not raise exceptions to avoid
        masking the original error that triggered the cleanup.
    """
    if not file_paths:
        return

    logger.info(f"Cleaning up {len(file_paths)} reference images from S3")

    for file_path in file_paths:
        try:
            # Run blocking S3 delete in thread pool to avoid blocking async event loop
            deleted = await asyncio.to_thread(delete_asset, file_path)
            if deleted:
                logger.info(f"Successfully deleted reference image: {file_path}")
            else:
                logger.warning(
                    f"Reference image not found during cleanup (may not have been uploaded): {file_path}"
                )
        except Exception as e:
            # Log but don't raise - we want to try deleting all files
            # and not mask the original error that caused the rollback
            logger.error(
                f"Failed to delete reference image {file_path} during cleanup: {e}"
            )


async def create_config(
    session: AsyncSession,
    project_id: uuid.UUID,
    request: CreateMonitoringConfigRequest,
) -> MonitoringConfig:
    """
    Create a new monitoring configuration.

    Args:
        session: Async database session.
        project_id: Project UUID from path parameter.
        request: Create request with monitoring configuration.

    Returns:
        The created MonitoringConfig.

    Raises:
        ValueError: If project or signal source not found, or name already exists.
    """
    project_repo = ProjectRepositoryAsync(session)
    source_repo = SignalSourceRepositoryAsync(session)
    config_repo = MonitoringConfigRepositoryAsync(session)

    # Verify project exists
    project = await project_repo.get_project(project_id)
    if not project:
        raise ValueError(f"Project {project_id} not found")

    # Verify signal source exists and belongs to project
    source = await source_repo.get_by_id(request.signal_source_id)
    if not source:
        raise ValueError(f"Signal source {request.signal_source_id} not found")

    if source.project_id != project_id and source.project_id is not None:
        raise ValueError(
            f"Signal source {request.signal_source_id} does not belong to project {project_id}"
        )

    # Check for duplicate name within project
    existing = await config_repo.get_by_name(project_id, request.name)
    if existing:
        raise ValueError(
            f"Monitoring config with name '{request.name}' already exists in project {project_id}"
        )

    # Create the monitoring config
    config = MonitoringConfig(
        project_id=project_id,
        signal_source_id=request.signal_source_id,
        name=request.name,
        description=request.description,
        rules=request.rules.model_dump(),
        enabled=request.enabled,
    )

    created_config = await config_repo.create(config)

    logger.info(
        f"Created monitoring config {created_config.id} for project {project_id}"
    )
    return created_config


async def get_configs(
    session: AsyncSession,
    project_id: uuid.UUID,
    enabled: bool | None = None,
    signal_source_id: uuid.UUID | None = None,
    page: int = 1,
    page_size: int = 10,
) -> tuple[list[MonitoringConfig], int]:
    """
    Get all monitoring configurations for a project.

    Args:
        session: Async database session.
        project_id: Project UUID.
        enabled: Optional filter by enabled status.
        signal_source_id: Optional filter by signal source.
        page: Page number (1-indexed).
        page_size: Items per page.

    Returns:
        Tuple of (list of MonitoringConfig objects, total count).

    Raises:
        ValueError: If project not found.
    """
    project_repo = ProjectRepositoryAsync(session)
    config_repo = MonitoringConfigRepositoryAsync(session)

    # Verify project exists
    project = await project_repo.get_project(project_id)
    if not project:
        raise ValueError(f"Project {project_id} not found")

    # Get all configs (filtering done in repository)
    all_configs = await config_repo.get_by_project(
        project_id, enabled=enabled, signal_source_id=signal_source_id
    )

    # Apply pagination
    total = len(all_configs)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_configs = all_configs[start_idx:end_idx]

    return paginated_configs, total


async def get_config(
    session: AsyncSession,
    project_id: uuid.UUID,
    config_id: uuid.UUID,
) -> MonitoringConfig | None:
    """
    Get a monitoring configuration by ID.

    Verifies the config belongs to the specified project.

    Args:
        session: Async database session.
        project_id: Project UUID.
        config_id: Config UUID.

    Returns:
        MonitoringConfig if found and belongs to project, None otherwise.
    """
    project_repo = ProjectRepositoryAsync(session)
    config_repo = MonitoringConfigRepositoryAsync(session)

    # Verify project exists
    project = await project_repo.get_project(project_id)
    if not project:
        return None

    config = await config_repo.get_by_id(config_id)

    # Verify config belongs to project
    if config and config.project_id == project_id:
        return config

    return None


async def update_config(
    session: AsyncSession,
    project_id: uuid.UUID,
    config_id: uuid.UUID,
    request: UpdateMonitoringConfigRequest,
) -> MonitoringConfig | None:
    """
    Update a monitoring configuration.

    Cannot change project_id or signal_source_id.

    Args:
        session: Async database session.
        project_id: Project UUID.
        config_id: Config UUID.
        request: Update request.

    Returns:
        Updated MonitoringConfig if found, None otherwise.

    Raises:
        ValueError: If name already exists (when changing name).
    """
    project_repo = ProjectRepositoryAsync(session)
    config_repo = MonitoringConfigRepositoryAsync(session)

    # Verify project exists
    project = await project_repo.get_project(project_id)
    if not project:
        return None

    # Verify config exists and belongs to project
    config = await config_repo.get_by_id(config_id)
    if not config or config.project_id != project_id:
        return None

    # Check for duplicate name if name is being changed
    if request.name is not None and request.name != config.name:
        existing = await config_repo.get_by_name(project_id, request.name)
        if existing:
            raise ValueError(
                f"Monitoring config with name '{request.name}' already exists in project {project_id}"
            )

    # Build updates
    updates = {}
    if request.name is not None:
        updates["name"] = request.name
    if request.description is not None:
        updates["description"] = request.description
    if request.rules is not None:
        updates["rules"] = request.rules.model_dump()
    if request.enabled is not None:
        updates["enabled"] = request.enabled

    if not updates:
        return config

    updated_config = await config_repo.update(config_id, **updates)
    logger.info(f"Updated monitoring config {config_id}")
    return updated_config


async def delete_config(
    session: AsyncSession,
    project_id: uuid.UUID,
    config_id: uuid.UUID,
) -> bool:
    """
    Delete a monitoring configuration.

    Args:
        session: Async database session.
        project_id: Project UUID.
        config_id: Config UUID.

    Returns:
        True if deleted, False if not found.
    """
    project_repo = ProjectRepositoryAsync(session)
    config_repo = MonitoringConfigRepositoryAsync(session)

    # Verify project exists
    project = await project_repo.get_project(project_id)
    if not project:
        return False

    # Verify config exists and belongs to project
    config = await config_repo.get_by_id(config_id)
    if not config or config.project_id != project_id:
        return False

    # Delete config
    deleted = await config_repo.delete(config_id)
    if deleted:
        logger.info(f"Deleted monitoring config {config_id}")

    return deleted


async def trigger_run(
    session: AsyncSession,
    project_id: uuid.UUID,
    config_id: uuid.UUID,
    user_id: str,
    s3_bucket: str | None = None,
    s3_key: str | None = None,
) -> MonitoringRun:
    """
    Trigger a manual monitoring run.

    Creates a run record with manual trigger metadata.
    Actual processing happens asynchronously.

    Args:
        session: Async database session.
        project_id: Project UUID.
        config_id: Config UUID.
        user_id: User who triggered the run.
        s3_bucket: Optional S3 bucket for image source.
        s3_key: Optional S3 key for image source.

    Returns:
        The created MonitoringRun.

    Raises:
        ValueError: If config not found or disabled.
    """
    config_repo = MonitoringConfigRepositoryAsync(session)
    run_repo = MonitoringRunRepositoryAsync(session)

    # Verify config exists, belongs to project, and is enabled
    config = await config_repo.get_by_id(config_id)
    if not config or config.project_id != project_id:
        raise ValueError(f"Monitoring config {config_id} not found")

    if not config.enabled:
        raise ValueError(f"Monitoring config {config_id} is disabled. Enable it first.")

    # Create trigger metadata
    trigger_metadata = {
        "trigger_source": "manual_api",
        "user_id": user_id,
        "endpoint": f"/api/v1/operation/monitoring/configs/{config_id}/run",
        "triggered_at": datetime.utcnow().isoformat(),
    }

    if s3_bucket and s3_key:
        trigger_metadata["s3_bucket"] = s3_bucket
        trigger_metadata["s3_key"] = s3_key

    # Create the run
    run = MonitoringRun(
        monitoring_config_id=config_id,
        trigger_metadata=trigger_metadata,
        started_at=datetime.utcnow(),
        evaluation_result={},  # Will be populated by processing worker
    )

    created_run = await run_repo.create(run)

    logger.info(
        f"Created monitoring run {created_run.id} for config {config_id} (manual trigger)"
    )

    # TODO: Enqueue for async processing
    # await enqueue_monitoring_run(created_run.id)

    return created_run


async def get_runs(
    session: AsyncSession,
    project_id: uuid.UUID,
    monitoring_config_id: uuid.UUID,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    result_filter: str | None = None,
    page: int = 1,
    page_size: int = 10,
) -> tuple[list[MonitoringRun], int]:
    """
    Get all monitoring runs for a configuration.

    Args:
        session: Async database session.
        project_id: Project UUID.
        monitoring_config_id: Monitoring config UUID.
        start_date: Optional filter for runs after this date.
        end_date: Optional filter for runs before this date.
        result_filter: Optional filter by result ('pass', 'fail', 'error').
        page: Page number (1-indexed).
        page_size: Items per page.

    Returns:
        Tuple of (list of MonitoringRun objects, total count).

    Raises:
        ValueError: If config not found or doesn't belong to project.
    """
    config_repo = MonitoringConfigRepositoryAsync(session)
    run_repo = MonitoringRunRepositoryAsync(session)

    # Verify config exists and belongs to project
    config = await config_repo.get_by_id(monitoring_config_id)
    if not config or config.project_id != project_id:
        raise ValueError(
            f"Monitoring config {monitoring_config_id} not found or doesn't belong to project {project_id}"
        )

    # Get all runs (filtering done in repository)
    all_runs = await run_repo.get_by_config(
        monitoring_config_id,
        start_date=start_date,
        end_date=end_date,
        result_filter=result_filter,
    )

    # Apply pagination
    total = len(all_runs)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_runs = all_runs[start_idx:end_idx]

    return paginated_runs, total


async def get_run(
    session: AsyncSession,
    project_id: uuid.UUID,
    run_id: uuid.UUID,
) -> MonitoringRun | None:
    """
    Get a monitoring run by ID.

    Verifies the run's config belongs to the specified project.

    Args:
        session: Async database session.
        project_id: Project UUID.
        run_id: Run UUID.

    Returns:
        MonitoringRun if found and belongs to project, None otherwise.
    """
    config_repo = MonitoringConfigRepositoryAsync(session)
    run_repo = MonitoringRunRepositoryAsync(session)

    run = await run_repo.get_by_id(run_id)
    if not run:
        return None

    # Verify the run's config belongs to the project
    config = await config_repo.get_by_id(run.monitoring_config_id)
    if config and config.project_id == project_id:
        return run

    return None


async def build_config_response(config: MonitoringConfig) -> MonitoringConfigResponse:
    """
    Build a MonitoringConfigResponse from a MonitoringConfig model.

    Args:
        config: MonitoringConfig database model.

    Returns:
        MonitoringConfigResponse for API response.
    """
    # Deep copy rules to avoid modifying the original
    transformed_rules = copy.deepcopy(config.rules)

    # Transform reference image URLs to presigned S3 URLs asynchronously
    if "reference_images" in transformed_rules:
        for image in transformed_rules["reference_images"]:
            if image.get("url"):
                original_url = image["url"]
                try:
                    # Run synchronous S3 operations in thread pool to avoid blocking event loop
                    image["url"] = await asyncio.to_thread(
                        map_uri_to_s3_url, original_url
                    )
                    # Preserve original URL if transformation fails (returns empty string)
                    if not image["url"]:
                        logger.warning(
                            f"Failed to transform URL {original_url}, preserving original"
                        )
                        image["url"] = original_url
                except Exception as e:
                    logger.error(
                        f"Error transforming URL {original_url}: {e}, preserving original"
                    )
                    image["url"] = original_url

    return MonitoringConfigResponse(
        id=config.id,
        project_id=config.project_id,
        signal_source_id=config.signal_source_id,
        name=config.name,
        description=config.description,
        rules=transformed_rules,
        enabled=config.enabled,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


def build_run_response(run: MonitoringRun) -> MonitoringRunResponse:
    """
    Build a MonitoringRunResponse from a MonitoringRun model.

    Args:
        run: MonitoringRun database model.

    Returns:
        MonitoringRunResponse for API response.
    """
    return MonitoringRunResponse(
        id=run.id,
        monitoring_config_id=run.monitoring_config_id,
        trigger_metadata=run.trigger_metadata,
        started_at=run.started_at,
        completed_at=run.completed_at,
        evaluation_result=run.evaluation_result,
        error_message=run.error_message,
    )
