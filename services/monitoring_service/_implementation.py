"""Monitoring Service Implementation.

Business logic for monitoring configuration and run CRUD operations.
"""

from __future__ import annotations

import asyncio
import copy
import os
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.operations.monitoring import (
    CreateMonitoringConfigRequest,
    MonitoringConfigResponse,
    MonitoringRunListResponse,
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

# AWS Configuration
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
AWS_ASSET_BUCKET_NAME = os.getenv("AWS_ASSET_BUCKET_NAME")


def build_structured_output_from_fields(
    response_fields: list[dict] | None,
) -> dict | None:
    """
    Build OpenAI-compatible JSON Schema from simple field definitions.

    Args:
        response_fields: List of field definitions with name, type, description, etc.

    Returns:
        JSON Schema dictionary ready for OpenAI Structured Outputs, or None if no fields

    Raises:
        ValueError: If field definitions are invalid
    """
    if not response_fields:
        return None

    # Validate field definitions
    field_names = [f["name"] for f in response_fields]
    if len(field_names) != len(set(field_names)):
        duplicates = [name for name in field_names if field_names.count(name) > 1]
        raise ValueError(f"Duplicate field names found: {set(duplicates)}")

    properties = {}
    required_fields = []

    for field in response_fields:
        field_name = field["name"]
        field_desc = field.get("description", "")
        is_required = field.get("required", True)

        # Build field schema - all fields are strings
        field_schema: dict = {
            "type": "string",
            "description": field_desc,
        }

        # Add enum if specified
        enum_values = field.get("enum_values")
        if enum_values:
            field_schema["enum"] = enum_values

        # Note: enum_metadata is used for UI display only and is not included
        # in the JSON Schema sent to the LLM (it's not a valid JSON Schema property)

        properties[field_name] = field_schema

        if is_required:
            required_fields.append(field_name)

    # Build complete schema
    schema = {
        "type": "object",
        "properties": properties,
        "required": required_fields,
        "additionalProperties": False,
    }

    return schema


async def upload_reference_images(
    images: list[UploadFile],
    descriptions: list[str],
    project_id: uuid.UUID,
    config_id: uuid.UUID,
    flags: list[str] | None = None,
) -> list[dict]:
    """
    Upload multiple reference images with descriptions to S3.

    Args:
        images: List of uploaded image files
        descriptions: List of descriptions for each image
        project_id: Project UUID
        config_id: Monitoring config UUID
        flags: Optional list of 'pass'/'fail' flags per image (defaults to 'pass')

    Returns:
        list[dict]: List of {"id": str, "url": str, "description": str, "flag": str} objects
            - id: UUID string for identifying the image
            - url: S3 file path
            - description: Image description
            - flag: 'pass' or 'fail' indicating what this image represents

    Raises:
        HTTPException: If image upload fails
    """
    uploaded_images = []

    # Validate flags if explicitly provided
    if flags is not None and len(flags) > 0:
        if len(flags) != len(images):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Number of reference_image_flags ({len(flags)}) must match "
                    f"number of images ({len(images)})"
                ),
            )
        invalid_flags = [flag for flag in flags if flag not in {"pass", "fail"}]
        if invalid_flags:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid reference_image_flags: {sorted(set(invalid_flags))}",
            )

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

            # Determine flag for this image
            image_flag = flags[idx] if flags and idx < len(flags) else "pass"

            # Return structured data with UUID for future reference
            uploaded_images.append(
                {
                    "id": str(image_uuid),
                    "url": file_path,
                    "description": description,
                    "flag": image_flag,
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

    # Prepare rules dict
    rules_dict = request.rules.model_dump()

    # Clean up monitoring_time_window: remove if None or disabled
    if "monitoring_time_window" in rules_dict:
        mtw = rules_dict["monitoring_time_window"]
        if mtw is None or not mtw.get("enabled", False):
            del rules_dict["monitoring_time_window"]

    # If structured_output fields are provided, build the schema
    if request.rules.structured_output:
        structured_output_fields = [
            field.model_dump() for field in request.rules.structured_output
        ]
        structured_output_schema = build_structured_output_from_fields(
            structured_output_fields
        )
        if structured_output_schema:
            rules_dict["structured_output"] = structured_output_schema

        # Store enum_metadata separately for UI display
        enum_metadata_map = {}
        for field_data in structured_output_fields:
            if "enum_metadata" in field_data and field_data["enum_metadata"]:
                enum_metadata_map[field_data["name"]] = field_data["enum_metadata"]

        if enum_metadata_map:
            rules_dict["enum_metadata_map"] = enum_metadata_map

    # Handle model config (part of rules)
    if request.model is not None:
        # Convert ModelConfig to dict, excluding None values
        model_dict = request.model.model_dump(exclude_none=True)
        if model_dict:
            rules_dict["model"] = model_dict
    else:
        # No model provided, use Azure as default
        rules_dict["model"] = {
            "provider": "azure",
            "model": "gpt-4o",
        }

    # Create the monitoring config
    config = MonitoringConfig(
        project_id=project_id,
        signal_source_id=request.signal_source_id,
        name=request.name,
        description=request.description,
        rules=rules_dict,
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
    add_image_flags: list[str] | None = None,
    remove_image_ids: list[str] | None = None,
    update_image_metadata: dict[str, dict[str, str]] | None = None,
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
        update_image_metadata: Dict mapping image_id -> metadata update map.
            Supported keys: "description", "flag".

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
        # Backward compat: when prompt is set, also update context
        current_rules["context"] = request.prompt
        updates["rules"] = current_rules

    # Handle context update (part of rules)
    if request.context is not None:
        current_rules = copy.deepcopy(
            updates.get("rules", config.rules if config.rules else {})
        )
        current_rules["context"] = request.context
        updates["rules"] = current_rules

    # Handle pass_criteria update (part of rules)
    if request.pass_criteria is not None:
        current_rules = copy.deepcopy(
            updates.get("rules", config.rules if config.rules else {})
        )
        current_rules["pass_criteria"] = request.pass_criteria
        updates["rules"] = current_rules

    # Handle fail_criteria update (part of rules)
    if request.fail_criteria is not None:
        current_rules = copy.deepcopy(
            updates.get("rules", config.rules if config.rules else {})
        )
        current_rules["fail_criteria"] = request.fail_criteria
        updates["rules"] = current_rules

    # Handle structured_output update (part of rules)
    if request.structured_output is not None:
        # Get current rules or initialize empty, preserving any already-staged updates (e.g., prompt)
        current_rules = copy.deepcopy(
            updates.get("rules", config.rules if config.rules else {})
        )

        # Build structured output schema from fields
        structured_output_fields = [
            field.model_dump() for field in request.structured_output
        ]

        # Check if the list is empty - if so, remove structured_output
        if not structured_output_fields:
            # Remove structured_output from rules if present
            if "structured_output" in current_rules:
                del current_rules["structured_output"]
            # Also remove enum_metadata_map if present
            if "enum_metadata_map" in current_rules:
                del current_rules["enum_metadata_map"]
        else:
            # Build and set the structured output schema
            structured_output_schema = build_structured_output_from_fields(
                structured_output_fields
            )
            if structured_output_schema:
                current_rules["structured_output"] = structured_output_schema

            # Store enum_metadata separately for UI display
            enum_metadata_map = {}
            for field_data in structured_output_fields:
                if "enum_metadata" in field_data and field_data["enum_metadata"]:
                    enum_metadata_map[field_data["name"]] = field_data["enum_metadata"]

            if enum_metadata_map:
                current_rules["enum_metadata_map"] = enum_metadata_map
            else:
                # Remove metadata if none provided in update
                if "enum_metadata_map" in current_rules:
                    del current_rules["enum_metadata_map"]

        updates["rules"] = current_rules

    # Handle model config update (part of rules)
    if request.model is not None:
        # Get current rules or initialize empty, preserving any already-staged updates
        current_rules = copy.deepcopy(
            updates.get("rules", config.rules if config.rules else {})
        )

        # Convert ModelConfig to dict, excluding None values
        model_dict = request.model.model_dump(exclude_none=True)

        # If model_dict is empty (all fields were None), remove model from rules
        if not model_dict:
            if "model" in current_rules:
                del current_rules["model"]
        else:
            # Set the model configuration
            current_rules["model"] = model_dict

        updates["rules"] = current_rules

    # Handle monitoring_time_window update (part of rules)
    if request.monitoring_time_window is not None:
        # Get current rules or initialize empty, preserving any already-staged updates
        current_rules = copy.deepcopy(
            updates.get("rules", config.rules if config.rules else {})
        )

        # Convert MonitoringTimeWindow to dict
        time_window_dict = request.monitoring_time_window.model_dump()

        # If time_window_dict only has enabled=False, remove from rules
        if not time_window_dict.get("enabled", False):
            if "monitoring_time_window" in current_rules:
                del current_rules["monitoring_time_window"]
        else:
            # Set the monitoring time window configuration
            current_rules["monitoring_time_window"] = time_window_dict

        updates["rules"] = current_rules

    # Handle reference image operations
    needs_image_update = add_images or remove_image_ids or update_image_metadata

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

        # Step 2: Update existing image metadata (no file upload)
        if update_image_metadata:
            for image_id, update_fields in update_image_metadata.items():
                if image_id in image_map:
                    if "description" in update_fields:
                        image_map[image_id]["description"] = update_fields[
                            "description"
                        ]
                        logger.info(
                            "Updated description for reference image %s in config %s",
                            image_id,
                            config_id,
                        )
                    if "flag" in update_fields:
                        image_map[image_id]["flag"] = update_fields["flag"]
                        logger.info(
                            "Updated flag for reference image %s in config %s",
                            image_id,
                            config_id,
                        )
                else:
                    logger.warning(
                        "Image ID %s not found for metadata update in config %s",
                        image_id,
                        config_id,
                    )

        # Step 3: Add new images
        if add_images:
            uploaded_images = await upload_reference_images(
                images=add_images,
                descriptions=add_descriptions or [],
                project_id=project_id,
                config_id=config_id,
                flags=add_image_flags or [],
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
    Delete a monitoring configuration, its associated runs, and clean up its S3 storage.

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

    # Delete associated monitoring runs before deleting config
    run_repo = MonitoringRunRepositoryAsync(session)
    runs = await run_repo.get_by_config(config_id)
    if runs:
        run_ids = [run.id for run in runs]
        delete_result = await run_repo.delete_batch(run_ids)
        logger.info(
            f"Deleted {delete_result['deleted']} monitoring runs for config {config_id}"
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
) -> list[MonitoringRun]:
    """
    Get all monitoring runs for a configuration.

    Args:
        session: Async database session.
        project_id: Project UUID.
        monitoring_config_id: Monitoring config UUID.
        start_date: Optional filter for runs after this date.
        end_date: Optional filter for runs before this date.
        result_filter: Optional filter by result ('pass', 'fail', 'error').

    Returns:
        List of MonitoringRun objects.

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

    return all_runs


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


async def delete_run(
    session: AsyncSession,
    project_id: uuid.UUID,
    run_id: uuid.UUID,
) -> bool:
    """
    Delete a monitoring run by ID.

    Verifies the run's config belongs to the specified project before deletion.

    Args:
        session: Async database session.
        project_id: Project UUID.
        run_id: Run UUID.

    Returns:
        True if deleted successfully, False if not found or unauthorized.
    """
    config_repo = MonitoringConfigRepositoryAsync(session)
    run_repo = MonitoringRunRepositoryAsync(session)

    # First verify the run exists and belongs to the project
    run = await run_repo.get_by_id(run_id)
    if not run:
        return False

    # Verify the run's config belongs to the project
    config = await config_repo.get_by_id(run.monitoring_config_id)
    if not config or config.project_id != project_id:
        return False

    # Delete the run
    return await run_repo.delete(run_id)


async def delete_runs_batch(
    session: AsyncSession,
    project_id: uuid.UUID,
    run_ids: list[uuid.UUID],
) -> dict[str, int]:
    """
    Delete multiple monitoring runs by IDs.

    Verifies each run's config belongs to the specified project before deletion.

    Args:
        session: Async database session.
        project_id: Project UUID.
        run_ids: List of run UUIDs to delete.

    Returns:
        Dictionary with 'deleted', 'not_found', and 'unauthorized' counts.
    """
    config_repo = MonitoringConfigRepositoryAsync(session)
    run_repo = MonitoringRunRepositoryAsync(session)

    authorized_run_ids = []
    not_found_count = 0
    unauthorized_count = 0

    # First, verify all runs exist and belong to the project
    for run_id in run_ids:
        run = await run_repo.get_by_id(run_id)
        if not run:
            not_found_count += 1
            continue

        # Verify the run's config belongs to the project
        config = await config_repo.get_by_id(run.monitoring_config_id)
        if not config or config.project_id != project_id:
            unauthorized_count += 1
            continue

        authorized_run_ids.append(run_id)

    # Delete all authorized runs
    if authorized_run_ids:
        result = await run_repo.delete_batch(authorized_run_ids)
        deleted_count = result["deleted"]
    else:
        deleted_count = 0

    return {
        "deleted": deleted_count,
        "not_found": not_found_count,
        "unauthorized": unauthorized_count,
    }


async def test_monitoring_config(
    session: AsyncSession,
    project_id: uuid.UUID,
    config_id: uuid.UUID,
    test_image_bytes: bytes | None = None,
    s3_url: str | None = None,
) -> dict:
    """
    Test a monitoring configuration without saving to database.

    Automatically detects whether the config is for image or video monitoring and
    uses the appropriate analysis method.

    For IMAGE configs:
    - Priority: uploaded file > S3 URL > latest feed capture
    - Supports uploaded test images, S3 URLs, or feed images

    For VIDEO configs:
    - Priority: S3 URL > latest feed capture
    - Supports S3 URLs or feed videos (no uploaded files)

    Args:
        session: Async database session.
        project_id: Project UUID.
        config_id: Monitoring config UUID.
        test_image_bytes: Optional raw image bytes from upload (only for image configs).
            Test images are NOT saved to S3 - they're passed directly to the LLM.
        s3_url: Optional S3 key/path to test media (supports both image and video configs).
            Examples: "security/cameras/account/project/camera/images/2026-03-12/image.jpg"
                     "security/cameras/account/project/camera/videos/2026-03-12/video.mp4"

    Returns:
        dict with keys matching MonitoringRun structure:
            - evaluation_result: dict that would be saved to DB (result, details, confidence)
            - error_message: str or None (extracted from evaluation_result when result='error')
            - prompt_sent: dict containing system instruction, user prompt, reference images structure
            - test_image_url: str describing the image/video source
            - test_image_source: descriptive string of source type

    Raises:
        ValueError: If config not found, doesn't belong to project, feed type unsupported,
            invalid parameters, or no recent capture available.
        HTTPException: If LLM analysis fails.
    """
    # Import here to avoid circular dependency
    from db.repositories import SignalFeedRepositoryAsync
    from db.tables.types import FeedType
    from services.monitoring_service._llm import (
        generate_monitoring_llm_prompt,
        generate_monitoring_video_llm_prompt,
    )

    config_repo = MonitoringConfigRepositoryAsync(session)

    # Verify config exists and belongs to project
    config = await config_repo.get_by_id(config_id)
    if not config or config.project_id != project_id:
        raise ValueError(
            f"Monitoring config {config_id} not found or doesn't belong to project {project_id}"
        )

    # Get signal feed to determine feed type (image vs video)
    feed_repo = SignalFeedRepositoryAsync(session)
    feed = await feed_repo.get_by_source_id(config.signal_source_id)
    if not feed:
        raise ValueError(
            f"No signal feed found for signal source {config.signal_source_id}"
        )

    # Detect media type from S3 URL if provided (overrides feed type)
    detected_media_type = None
    if s3_url:
        s3_url_lower = s3_url.lower()
        video_extensions = (
            ".mkv",
            ".mp4",
            ".mov",
            ".avi",
            ".webm",
            ".flv",
            ".mpg",
            ".wmv",
            ".3gp",
        )
        image_extensions = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp")

        if s3_url_lower.endswith(video_extensions):
            detected_media_type = "video"
            logger.info(
                f"[Test Monitoring Config] Detected video file from S3 URL extension: {s3_url}",
                extra={
                    "config_id": str(config_id),
                    "s3_url": s3_url,
                    "detected_type": "video",
                },
            )
        elif s3_url_lower.endswith(image_extensions):
            detected_media_type = "image"
            logger.info(
                f"[Test Monitoring Config] Detected image file from S3 URL extension: {s3_url}",
                extra={
                    "config_id": str(config_id),
                    "s3_url": s3_url,
                    "detected_type": "image",
                },
            )

    # Route to appropriate testing logic based on detected media type or feed type
    use_video_flow = (
        detected_media_type == "video"
        if detected_media_type
        else feed.feed_type == FeedType.video_stream
    )

    if use_video_flow:
        # VIDEO MONITORING TEST
        logger.info(
            f"[Test Monitoring Config] Detected video monitoring config {config_id}",
            extra={
                "config_id": str(config_id),
                "project_id": str(project_id),
                "signal_source_id": str(config.signal_source_id),
                "feed_type": "video_stream",
            },
        )

        # Video test doesn't support uploaded test files - only S3 URLs or feed videos
        if test_image_bytes is not None:
            raise ValueError(
                "Uploaded test files are not supported for video monitoring configs. "
                "Please provide an s3_url or the test will use the latest captured video from the camera feed."
            )

        # Determine which video to use for testing
        # Priority: S3 URL > latest feed capture
        if s3_url:
            # Use provided S3 URL
            video_url = s3_url
            video_source = "s3_url"
            logger.info(
                f"[Test Monitoring Config] Testing video config {config_id} with S3 URL {video_url}",
                extra={
                    "config_id": str(config_id),
                    "project_id": str(project_id),
                    "signal_source_id": str(config.signal_source_id),
                    "test_video_url": video_url,
                    "source": video_source,
                },
            )
        else:
            # Fall back to latest feed capture
            if not feed.last_capture_url:
                raise ValueError(
                    "No recent video available from camera and no s3_url provided. "
                    "Please provide an s3_url or wait for the next camera capture."
                )

            video_url = feed.last_capture_url
            video_source = "signal_feed"
            logger.info(
                f"[Test Monitoring Config] Testing video config {config_id} with latest feed video {video_url}",
                extra={
                    "config_id": str(config_id),
                    "project_id": str(project_id),
                    "signal_source_id": str(config.signal_source_id),
                    "test_video_url": video_url,
                    "source": video_source,
                    "last_capture_at": (
                        feed.last_capture_at.isoformat()
                        if feed.last_capture_at
                        else None
                    ),
                },
            )

        # Run video LLM analysis
        llm_result = await generate_monitoring_video_llm_prompt(
            session=session,
            monitoring_config_id=config_id,
            video_url=video_url,
        )

        analysis_result = llm_result.get("analysis_result", {})
        result_status = analysis_result.get("result")

        # Extract error_message if result is "error"
        error_message = None
        if result_status == "error":
            error_message = analysis_result.get("details", "Video validation failed")

        logger.info(
            f"[Test Monitoring Config] Video analysis completed for config {config_id}",
            extra={
                "config_id": str(config_id),
                "result": result_status,
                "error_message": error_message,
                "test_video_url": video_url,
            },
        )

        # Return data structure matching MonitoringRun table
        return {
            "evaluation_result": analysis_result,
            "error_message": error_message,
            "prompt_sent": llm_result.get("prompt_sent", {}),
            "test_image_url": video_url,  # S3 path to video
            "test_image_source": video_url,  # Video S3 path (from s3_url or feed)
        }

    else:
        # IMAGE MONITORING TEST
        logger.info(
            f"[Test Monitoring Config] Using image monitoring flow for config {config_id}",
            extra={
                "config_id": str(config_id),
                "project_id": str(project_id),
                "signal_source_id": str(config.signal_source_id),
                "detected_media_type": detected_media_type,
                "feed_type": feed.feed_type.value if feed.feed_type else None,
            },
        )

        # Determine which image to use for testing
        # Priority: uploaded file > S3 URL > latest feed capture
        if test_image_bytes is not None:
            # Validate that uploaded image is not empty
            if len(test_image_bytes) == 0:
                raise ValueError("Uploaded test image is empty (0 bytes)")

            # Use the provided custom test image bytes (not saved to S3)
            image_url = None
            image_source = "custom_upload"
            image_description = "uploaded test image"
            logger.info(
                f"[Test Monitoring Config] Testing configuration {config_id} with uploaded image",
                extra={
                    "config_id": str(config_id),
                    "project_id": str(project_id),
                    "signal_source_id": str(config.signal_source_id),
                    "image_source": image_source,
                    "image_size_bytes": len(test_image_bytes),
                },
            )
        elif s3_url:
            # Use provided S3 URL
            image_url = s3_url
            image_source = "s3_url"
            image_description = s3_url
            logger.info(
                f"[Test Monitoring Config] Testing configuration {config_id} with S3 URL {image_url}",
                extra={
                    "config_id": str(config_id),
                    "project_id": str(project_id),
                    "signal_source_id": str(config.signal_source_id),
                    "test_image_url": image_url,
                    "image_source": image_source,
                },
            )
        else:
            # Fall back to latest image from signal feed
            if not feed.last_capture_url:
                raise ValueError(
                    "No recent image available from camera, no s3_url provided, and no test image uploaded. "
                    "Please provide a test_image file, s3_url, or wait for the next camera capture."
                )

            image_url = feed.last_capture_url
            image_source = "signal_feed"
            image_description = feed.last_capture_url
            logger.info(
                f"[Test Monitoring Config] Testing configuration {config_id} with latest feed image {image_url}",
                extra={
                    "config_id": str(config_id),
                    "project_id": str(project_id),
                    "signal_source_id": str(config.signal_source_id),
                    "test_image_url": image_url,
                    "image_source": image_source,
                    "last_capture_at": (
                        feed.last_capture_at.isoformat()
                        if feed.last_capture_at
                        else None
                    ),
                },
            )

        # Run LLM analysis using existing monitoring logic
        # This returns {"prompt_sent": {...}, "analysis_result": {...}}
        llm_result = await generate_monitoring_llm_prompt(
            session=session,
            monitoring_config_id=config_id,
            image_url=image_url,
            image_bytes=test_image_bytes,
        )

        analysis_result = llm_result.get("analysis_result", {})
        result_status = analysis_result.get("result")

        # Extract error_message if result is "error"
        error_message = None
        if result_status == "error":
            error_message = analysis_result.get("details", "Image validation failed")

        logger.info(
            f"[Test Monitoring Config] Image analysis completed for config {config_id}",
            extra={
                "config_id": str(config_id),
                "result": result_status,
                "error_message": error_message,
                "test_image_url": image_url,
                "test_image_source": image_description,
            },
        )

        # Return data structure matching MonitoringRun table
        return {
            "evaluation_result": analysis_result,
            "error_message": error_message,
            "prompt_sent": llm_result.get("prompt_sent", {}),
            "test_image_url": image_url,  # S3 path or None for uploaded images
            "test_image_source": image_description,  # Descriptive string
        }


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

    Extracts the image S3 key from trigger_metadata and converts it to a presigned URL.

    Args:
        run: MonitoringRun database model.

    Returns:
        MonitoringRunResponse for API response.
    """
    # Extract S3 key from trigger metadata
    image_s3_key = None
    if run.trigger_metadata:
        # Check for s3_key in trigger metadata
        s3_key = run.trigger_metadata.get("s3_key")
        if s3_key:
            image_s3_key = s3_key

    # Convert S3 key to presigned URL
    image_url = map_uri_to_s3_url(image_s3_key) if image_s3_key else None

    return MonitoringRunResponse(
        id=run.id,
        monitoring_config_id=run.monitoring_config_id,
        image_url=image_url,
        started_at=run.started_at,
        completed_at=run.completed_at,
        evaluation_result=run.evaluation_result,
        error_message=run.error_message,
    )


def build_run_list_response(run: MonitoringRun) -> MonitoringRunListResponse:
    """
    Build a MonitoringRunListResponse from a MonitoringRun model.

    This is optimized for list views and does not include image URLs to avoid
    S3 API calls for every run in the list.

    Args:
        run: MonitoringRun database model.

    Returns:
        MonitoringRunListResponse for API response (without image_url).
    """
    return MonitoringRunListResponse(
        id=run.id,
        monitoring_config_id=run.monitoring_config_id,
        started_at=run.started_at,
        completed_at=run.completed_at,
        evaluation_result=run.evaluation_result,
        error_message=run.error_message,
    )


async def _rerun_monitoring_analysis_background(
    run_id: uuid.UUID,
    monitoring_config_id: uuid.UUID,
    media_url: str,
    is_video: bool,
) -> None:
    """
    Background task to rerun monitoring analysis and update the run record.

    This function runs the LLM analysis in the background and updates the
    evaluation_result field when complete. The completed_at timestamp is
    preserved from the original run.

    Args:
        run_id: UUID of the monitoring run to update
        monitoring_config_id: UUID of the monitoring configuration
        media_url: S3 key/path of the media to analyze (image or video)
        is_video: True if this is a video analysis, False for image
    """
    from db import get_db_async

    try:
        # Create a new database session for this background task
        async for session in get_db_async():
            run_repo = MonitoringRunRepositoryAsync(session)
            try:

                # Run the analysis
                if is_video:
                    # Import here to avoid circular dependency
                    from services.monitoring_service._llm import (
                        generate_monitoring_video_llm_prompt,
                    )

                    logger.info(
                        f"[Rerun Background] Running video analysis for run {run_id}",
                        extra={
                            "run_id": str(run_id),
                            "config_id": str(monitoring_config_id),
                            "video_url": media_url,
                        },
                    )

                    llm_result = await generate_monitoring_video_llm_prompt(
                        session=session,
                        monitoring_config_id=monitoring_config_id,
                        video_url=media_url,
                    )
                else:
                    # Import here to avoid circular dependency
                    from services.monitoring_service._llm import (
                        generate_monitoring_llm_prompt,
                    )

                    logger.info(
                        f"[Rerun Background] Running image analysis for run {run_id}",
                        extra={
                            "run_id": str(run_id),
                            "config_id": str(monitoring_config_id),
                            "image_url": media_url,
                        },
                    )

                    llm_result = await generate_monitoring_llm_prompt(
                        session=session,
                        monitoring_config_id=monitoring_config_id,
                        image_url=media_url,
                    )

                analysis_result = llm_result.get("analysis_result", {})
                result_status = analysis_result.get("result")

                # Extract error_message if result is "error"
                error_message = None
                if result_status == "error":
                    error_message = analysis_result.get(
                        "details",
                        f"{'Video' if is_video else 'Image'} validation failed",
                    )

                # Update the run with new results (keeping completed_at unchanged)
                await run_repo.update(
                    run_id,
                    evaluation_result=analysis_result,
                    error_message=error_message,
                )

                await session.commit()

                logger.info(
                    f"[Rerun Background] Analysis completed for run {run_id}",
                    extra={
                        "run_id": str(run_id),
                        "config_id": str(monitoring_config_id),
                        "result": result_status,
                        "error_message": error_message,
                    },
                )

            except Exception as e:
                logger.error(
                    f"[Rerun Background] Error during analysis for run {run_id}: {e}",
                    exc_info=True,
                    extra={
                        "run_id": str(run_id),
                        "config_id": str(monitoring_config_id),
                    },
                )
                await session.rollback()

                # Update run with error status
                try:
                    await run_repo.update(
                        run_id,
                        evaluation_result={
                            "result": "error",
                            "details": f"Rerun failed: {str(e)}",
                            "status": "failed",
                        },
                        error_message=f"Rerun failed: {str(e)}",
                    )
                    await session.commit()
                except Exception as update_error:
                    logger.error(
                        f"[Rerun Background] Failed to update run with error status: {update_error}",
                        extra={"run_id": str(run_id)},
                    )

            finally:
                # Session is automatically closed by the async generator
                break

    except Exception as e:
        logger.error(
            f"[Rerun Background] Fatal error in background task for run {run_id}: {e}",
            exc_info=True,
        )


async def rerun_monitoring_run(
    session: AsyncSession,
    project_id: uuid.UUID,
    run_id: uuid.UUID,
) -> dict:
    """
    Rerun a monitoring run analysis and return immediately with processing status.

    This function:
    1. Fetches the existing monitoring run
    2. Determines if it's video or image based on the monitoring config
    3. Sets the evaluation_result to "processing" status
    4. Triggers background analysis that will update the result when complete
    5. Returns immediately without waiting for analysis

    The completed_at timestamp is preserved from the original run.

    Args:
        session: Async database session
        project_id: Project UUID (for authorization)
        run_id: UUID of the monitoring run to rerun

    Returns:
        dict with run_id, monitoring_config_id, and status

    Raises:
        ValueError: If run not found, doesn't belong to project, or missing media URL
    """
    from db.repositories import SignalFeedRepositoryAsync
    from db.tables.types import FeedType

    run_repo = MonitoringRunRepositoryAsync(session)
    config_repo = MonitoringConfigRepositoryAsync(session)

    # Fetch the existing run
    run = await run_repo.get_by_id(run_id)
    if not run:
        raise ValueError(f"Monitoring run {run_id} not found")

    # Fetch the monitoring config to verify project access
    config = await config_repo.get_by_id(run.monitoring_config_id)
    if not config:
        raise ValueError(
            f"Monitoring config {run.monitoring_config_id} not found for run {run_id}"
        )

    if config.project_id != project_id:
        raise ValueError(
            f"Monitoring run {run_id} does not belong to project {project_id}"
        )

    # Determine media URL from trigger_metadata
    trigger_metadata = run.trigger_metadata or {}
    media_url = (
        trigger_metadata.get("image_url")
        or trigger_metadata.get("video_url")
        or trigger_metadata.get("s3_key")
    )

    if not media_url:
        raise ValueError(
            f"No media URL found in run {run_id} trigger_metadata. "
            f"Checked image_url, video_url, and s3_key. "
            f"Cannot rerun analysis without original media reference."
        )

    # Determine if this is video or image based on signal feed type
    feed_repo = SignalFeedRepositoryAsync(session)
    feed = await feed_repo.get_by_source_id(config.signal_source_id)
    if not feed:
        raise ValueError(
            f"No signal feed found for signal source {config.signal_source_id}"
        )

    is_video = feed.feed_type == FeedType.video_stream

    logger.info(
        f"[Rerun] Starting rerun for monitoring run {run_id}",
        extra={
            "run_id": str(run_id),
            "config_id": str(run.monitoring_config_id),
            "project_id": str(project_id),
            "media_url": media_url,
            "is_video": is_video,
            "feed_type": feed.feed_type.value,
        },
    )

    # Update evaluation_result to show processing status
    processing_result = {
        "result": "processing",
        "status": "rerunning",
        "details": "Analysis is being rerun. Results will be updated when complete.",
        "rerun_started_at": datetime.now(timezone.utc).isoformat(),
    }

    await run_repo.update(
        run_id,
        evaluation_result=processing_result,
        error_message=None,
    )

    await session.commit()

    # Trigger background analysis (fire and forget)
    asyncio.create_task(
        _rerun_monitoring_analysis_background(
            run_id=run_id,
            monitoring_config_id=run.monitoring_config_id,
            media_url=media_url,
            is_video=is_video,
        )
    )

    logger.info(
        f"[Rerun] Rerun queued for monitoring run {run_id}, returning immediately",
        extra={
            "run_id": str(run_id),
            "config_id": str(run.monitoring_config_id),
            "status": "processing",
        },
    )

    return {
        "run_id": run_id,
        "monitoring_config_id": run.monitoring_config_id,
        "status": "processing",
    }
