"""Monitoring Service Implementation.

Business logic for monitoring configuration and run CRUD operations.
"""

from __future__ import annotations

import asyncio
import base64
import copy
import json
import os
import uuid
from datetime import datetime

import boto3
import openai
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

# OpenAI Configuration
OPENAI_MODEL = "gpt-4o"
OPENAI_MAX_TOKENS = 2000
OPENAI_RESPONSE_FORMAT = {"type": "json_object"}
OPENAI_IMAGE_DETAIL = "high"

# AWS Configuration
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
AWS_ASSET_BUCKET_NAME = os.getenv("AWS_ASSET_BUCKET_NAME")


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
        list[dict]: List of {"id": str, "url": str, "description": str} objects
            - id: UUID string for identifying the image
            - url: S3 file path
            - description: Image description

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

            # Return structured data with UUID for future reference
            uploaded_images.append(
                {
                    "id": str(image_uuid),
                    "url": file_path,
                    "description": description,
                }
            )

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
    add_images: list[UploadFile] | None = None,
    add_descriptions: list[str] | None = None,
    remove_image_ids: list[str] | None = None,
    update_descriptions: dict[str, str] | None = None,
) -> tuple[MonitoringConfig | None, list[str]]:
    """
    Update a monitoring configuration with simple operation-based image management.

    Send only the operations you want to perform:
    - Add new images
    - Remove existing images by ID
    - Update descriptions without touching the image file

    Cannot change project_id or signal_source_id.

    Args:
        session: Async database session.
        project_id: Project UUID.
        config_id: Config UUID.
        request: Update request.
        add_images: New image files to add.
        add_descriptions: Descriptions for new images.
        remove_image_ids: List of image UUIDs to remove.
        update_descriptions: Dict mapping image_id -> new_description.

    Returns:
        Tuple of (Updated MonitoringConfig if found, list of S3 URLs to delete).
        The S3 URLs should be deleted AFTER the database transaction commits.

    Raises:
        ValueError: If name already exists or invalid image operations.
    """
    project_repo = ProjectRepositoryAsync(session)
    config_repo = MonitoringConfigRepositoryAsync(session)

    # Verify project exists
    project = await project_repo.get_project(project_id)
    if not project:
        return None, []

    # Verify config exists and belongs to project
    config = await config_repo.get_by_id(config_id)
    if not config or config.project_id != project_id:
        return None, []

    # Check for duplicate name if name is being changed
    if request.name is not None and request.name != config.name:
        existing = await config_repo.get_by_name(project_id, request.name)
        if existing:
            raise ValueError(
                f"Monitoring config with name '{request.name}' already exists in project {project_id}"
            )

    # Validate add operations - both add_images and add_descriptions must be provided together
    has_add_images = bool(add_images and len(add_images) > 0)
    has_add_descriptions = bool(add_descriptions and len(add_descriptions) > 0)

    if has_add_images != has_add_descriptions:
        raise ValueError(
            "Both add_images and add_descriptions must be provided together. "
            f"Got add_images: {has_add_images}, add_descriptions: {has_add_descriptions}"
        )

    if has_add_images and has_add_descriptions:
        if len(add_images) != len(add_descriptions):  # type: ignore[arg-type]
            raise ValueError(
                f"Number of add_images ({len(add_images)}) must match "  # type: ignore[arg-type]
                f"number of add_descriptions ({len(add_descriptions)})"  # type: ignore[arg-type]
            )

    # Track S3 URLs to delete (return these to caller for cleanup after commit)
    images_to_delete: list[str] = []

    # Build updates
    updates = {}
    if request.name is not None:
        updates["name"] = request.name
    if request.description is not None:
        updates["description"] = request.description
    if request.enabled is not None:
        updates["enabled"] = request.enabled

    # Handle prompt update (part of rules)
    if request.prompt is not None:
        # Get current rules or initialize empty
        current_rules = copy.deepcopy(config.rules) if config.rules else {}
        current_rules["prompt"] = request.prompt
        updates["rules"] = current_rules

    # Handle reference image operations
    needs_image_update = add_images or remove_image_ids or update_descriptions

    if needs_image_update:
        # Get current reference images, preserving any already-staged rule updates (e.g., prompt)
        current_rules = copy.deepcopy(
            updates.get("rules", config.rules if config.rules else {})
        )
        current_images = current_rules.get("reference_images", [])

        # Build a map of image_id -> image for quick lookup
        image_map = {
            img.get("id"): img
            for img in current_images
            if isinstance(img, dict) and "id" in img
        }

        # Step 1: Remove images by ID
        if remove_image_ids:
            for image_id in remove_image_ids:
                if image_id in image_map:
                    removed_img = image_map.pop(image_id)
                    if "url" in removed_img:
                        images_to_delete.append(removed_img["url"])
                    logger.info(
                        f"Removed reference image {image_id} from config {config_id}"
                    )
                else:
                    logger.warning(
                        f"Image ID {image_id} not found for removal in config {config_id}"
                    )

        # Step 2: Update descriptions (no file upload)
        if update_descriptions:
            for image_id, new_desc in update_descriptions.items():
                if image_id in image_map:
                    image_map[image_id]["description"] = new_desc
                    logger.info(
                        f"Updated description for reference image {image_id} in config {config_id}"
                    )
                else:
                    logger.warning(
                        f"Image ID {image_id} not found for description update in config {config_id}"
                    )

        # Step 3: Add new images
        if add_images:
            uploaded_images = await upload_reference_images(
                images=add_images,
                descriptions=add_descriptions or [],
                project_id=project_id,
                config_id=config_id,
            )
            # Add to map
            for img in uploaded_images:
                if "id" in img:
                    image_map[img["id"]] = img
            logger.info(
                f"Added {len(uploaded_images)} new reference images to config {config_id}"
            )

        # Rebuild current_images list from map (preserves order for existing, adds new at end)
        # First keep existing images in their original order
        existing_ids = [
            img.get("id")
            for img in current_images
            if isinstance(img, dict) and "id" in img and img.get("id") in image_map
        ]
        current_images = [
            image_map[img_id] for img_id in existing_ids if img_id in image_map
        ]

        # Add any new images that weren't in the original list (preserves insertion order)
        new_ids = [k for k in image_map.keys() if k not in existing_ids]
        current_images.extend([image_map[img_id] for img_id in new_ids])

        # Update rules with modified reference images
        current_rules["reference_images"] = current_images
        updates["rules"] = current_rules

    if not updates:
        return config, []

    updated_config = await config_repo.update(config_id, **updates)

    logger.info(f"Updated monitoring config {config_id}")

    # Return config and list of S3 URLs to delete
    return updated_config, images_to_delete


async def delete_config(
    session: AsyncSession,
    project_id: uuid.UUID,
    config_id: uuid.UUID,
) -> bool:
    """
    Delete a monitoring configuration and clean up its S3 storage.

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

    # Extract reference image URLs before deletion for S3 cleanup
    file_paths: list[str] = []
    if config.rules and "reference_images" in config.rules:
        reference_images = config.rules.get("reference_images", [])
        file_paths = [
            img["url"]
            for img in reference_images
            if isinstance(img, dict) and "url" in img
        ]
        logger.info(
            f"Found {len(file_paths)} reference images to clean up for config {config_id}"
        )

    # Delete config from database
    deleted = await config_repo.delete(config_id)
    if deleted:
        logger.info(f"Deleted monitoring config {config_id}")

        # Clean up S3 storage after successful database deletion
        if file_paths:
            await cleanup_reference_images(file_paths)

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


async def generate_monitoring_llm_prompt(
    session: AsyncSession,
    monitoring_config_id: uuid.UUID,
    image_url: str,
) -> dict:
    """
    Execute LLM analysis for a monitoring configuration.

    Retrieves the monitoring config, fetches reference images and camera image,
    and performs AI analysis using OpenAI Vision API.

    Args:
        session: Async database session
        monitoring_config_id: UUID of the monitoring configuration
        image_url: S3 key/path of the camera image to analyze

    Returns:
        dict: Contains both the prompt and analysis result:
            {
                "prompt_sent": {
                    "system_instruction": str,
                    "user_prompt": str,
                    "reference_images": [{"description": str}],
                    "camera_image_included": bool
                },
                "analysis_result": {
                    "result": "pass" or "fail",
                    "confidence": 0.0-1.0,
                    "finding": str,
                    "details": {...}
                }
            }

    Raises:
        HTTPException: If config not found or S3/OpenAI errors occur
    """
    # Get monitoring config
    config_repo = MonitoringConfigRepositoryAsync(session)
    config = await config_repo.get_by_id(monitoring_config_id)

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitoring config {monitoring_config_id} not found",
        )

    # Initialize S3 client
    s3_client = (
        boto3.client(
            "s3",
            region_name=AWS_REGION,
            aws_access_key_id=os.getenv("LOCAL_AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("LOCAL_AWS_SECRET_ACCESS_KEY"),
            aws_session_token=os.getenv("LOCAL_AWS_SESSION_TOKEN"),
        )
        if os.getenv("LOCAL_AWS_ACCESS_KEY_ID")
        else boto3.client("s3", region_name=AWS_REGION)
    )

    # Fetch camera image from S3
    try:
        # Run blocking S3 operations in thread pool to avoid blocking event loop
        camera_response = await asyncio.to_thread(
            s3_client.get_object, Bucket=AWS_ASSET_BUCKET_NAME, Key=image_url
        )
        camera_image_content = await asyncio.to_thread(camera_response["Body"].read)
        camera_image_base64 = base64.b64encode(camera_image_content).decode("utf-8")
    except Exception as e:
        logger.error(f"Failed to retrieve camera image from S3: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve camera image from storage",
        ) from e

    # Build prompt from rules
    rules = config.rules or {}
    prompt = rules.get("prompt", "")
    reference_images_meta = rules.get("reference_images", [])

    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Monitoring config has no prompt in rules",
        )

    # Fetch reference images if specified
    reference_images_base64 = []
    for ref_img in reference_images_meta:
        ref_image_url = ref_img.get("url")
        description = ref_img.get("description", "Reference image")

        if not ref_image_url:
            logger.warning("Reference image missing 'url' field, skipping")
            continue

        try:
            # Run blocking S3 operations in thread pool to avoid blocking event loop
            ref_response = await asyncio.to_thread(
                s3_client.get_object, Bucket=AWS_ASSET_BUCKET_NAME, Key=ref_image_url
            )
            ref_content = await asyncio.to_thread(ref_response["Body"].read)
            ref_base64 = base64.b64encode(ref_content).decode("utf-8")
            reference_images_base64.append(
                {
                    "base64": ref_base64,
                    "description": description,
                }
            )
        except Exception as e:
            logger.warning(f"Failed to retrieve reference image {ref_image_url}: {e}")
            # Continue without this reference image

    # Build OpenAI messages with images - structured as a vision analysis prompt
    system_instruction = """You are a visual monitoring assistant. Your task is to analyze a camera image and compare it against reference images to detect any issues or anomalies.

Please analyze the images carefully and respond with a JSON object containing:
- "result": either "pass" or "fail"
- "confidence": a number between 0 and 1 indicating your confidence
- "finding": a brief description of what you observed
- "details": any additional relevant details about your analysis"""

    message_content: list[dict] = [
        {"type": "text", "text": system_instruction},
        {"type": "text", "text": f"\n**Analysis Task:**\n{prompt}\n"},
    ]

    # Add reference images with context
    if reference_images_base64:
        message_content.append(
            {"type": "text", "text": "\n**Reference Images (Expected State):**"}
        )
        for idx, ref_img in enumerate(reference_images_base64):
            message_content.append(
                {
                    "type": "text",
                    "text": f"\nReference {idx + 1}: {ref_img['description']}",
                }
            )
            message_content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{ref_img['base64']}",
                        "detail": OPENAI_IMAGE_DETAIL,
                    },
                }
            )

    # Add camera image to analyze
    message_content.append(
        {
            "type": "text",
            "text": "\n**Current Camera Image (To Be Analyzed):**\nPlease compare this image against the reference images above and evaluate based on the analysis task.",
        }
    )
    message_content.append(
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{camera_image_base64}",
                "detail": OPENAI_IMAGE_DETAIL,
            },
        }
    )

    # Call OpenAI Vision API
    try:
        # Run blocking OpenAI call in thread pool
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: openai.OpenAI().chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "user", "content": message_content}],  # type: ignore[arg-type]
                response_format=OPENAI_RESPONSE_FORMAT,  # type: ignore[arg-type]
                max_tokens=OPENAI_MAX_TOKENS,
            ),
        )

        analysis_result = json.loads(response.choices[0].message.content or "{}")

        logger.info(
            f"Monitoring LLM analysis completed for config {monitoring_config_id}",
            extra={
                "config_id": str(monitoring_config_id),
                "result": analysis_result.get("result", "unknown"),
            },
        )

        # Build prompt summary (excluding base64 data for readability)
        prompt_summary = {
            "system_instruction": system_instruction,
            "user_prompt": prompt,
            "reference_images": [
                {"description": ref_img["description"]}
                for ref_img in reference_images_base64
            ],
            "camera_image_included": True,
        }

        return {
            "prompt_sent": prompt_summary,
            "analysis_result": analysis_result,
        }

    except Exception as e:
        logger.error(f"OpenAI API call failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LLM analysis failed: {str(e)}",
        )
