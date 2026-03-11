"""Monitoring API Routes Implementation.

Business logic handlers for monitoring configuration and run CRUD endpoints.
"""

from __future__ import annotations

import asyncio
import math
import uuid
from datetime import datetime

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import attributes

from api.schemas.operations.monitoring import (
    BatchDeleteMonitoringRunsRequest,
    BatchDeleteMonitoringRunsResponse,
    CreateMonitoringConfigRequest,
    ListMonitoringConfigsResponse,
    ListMonitoringRunsResponse,
    MonitoringConfigResponse,
    MonitoringRunResponse,
    TestMonitoringConfigResponse,
    TriggerRunRequest,
    TriggerRunResponse,
    UpdateMonitoringConfigRequest,
)
from services import monitoring_service
from utils.log import logger


async def create_monitoring_config(
    project_id: uuid.UUID,
    request: CreateMonitoringConfigRequest,
    reference_images: list[UploadFile],
    reference_image_descriptions: list[str],
    session: AsyncSession,
    reference_image_flags: list[str] | None = None,
) -> MonitoringConfigResponse:
    """
    Create a new monitoring configuration with optional reference image uploads.

    Args:
        project_id: Project UUID from path parameter.
        request: Create request with monitoring configuration.
        reference_images: List of reference image files to upload.
        reference_image_descriptions: List of descriptions for each reference image.
        session: Async database session.

    Returns:
        Created MonitoringConfigResponse.

    Raises:
        HTTPException: If creation fails.
    """
    uploaded_file_paths: list[str] = []

    try:
        config = await monitoring_service.create_config(
            session=session,
            project_id=project_id,
            request=request,
        )

        # Upload reference images if provided
        if reference_images:
            # Store config_id before S3 upload to avoid MissingGreenlet error
            # asyncio.to_thread() in upload function can't access SQLAlchemy objects
            config_id = config.id

            uploaded_images = await monitoring_service.upload_reference_images(
                images=reference_images,
                descriptions=reference_image_descriptions,
                project_id=project_id,
                config_id=config_id,
                flags=reference_image_flags or [],
            )

            # Track uploaded file paths for potential rollback
            uploaded_file_paths = [img["url"] for img in uploaded_images]

            # Refresh config to re-establish async session context after asyncio.to_thread()
            await session.refresh(config)

            # Update config with structured reference images
            config.rules["reference_images"] = uploaded_images
            # Mark the JSONB field as modified so SQLAlchemy tracks the change
            attributes.flag_modified(config, "rules")

        await session.commit()

        # Refresh to reload attributes after commit and avoid greenlet_spawn error
        await session.refresh(config)

        response = await monitoring_service.build_config_response(config)
        logger.info(
            "[create monitoring config] Created config %s for project %s",
            config.id,
            project_id,
        )
        return response

    except ValueError as e:
        logger.error(
            f"[create monitoring config] Validation error creating monitoring config "
            f"for project {project_id}: {e}"
        )
        await session.rollback()
        # Clean up any uploaded S3 files
        if uploaded_file_paths:
            await monitoring_service.cleanup_reference_images(uploaded_file_paths)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except HTTPException as e:
        logger.error(
            f"[create monitoring config] HTTP error creating monitoring config "
            f"for project {project_id}: status={e.status_code}, detail={e.detail}"
        )
        await session.rollback()
        # Clean up any uploaded S3 files
        if uploaded_file_paths:
            await monitoring_service.cleanup_reference_images(uploaded_file_paths)
        raise
    except Exception as e:
        logger.error(
            f"[create monitoring config] Unexpected error creating monitoring config "
            f"for project {project_id}: {e}",
            exc_info=True,
        )
        await session.rollback()
        # Clean up any uploaded S3 files
        if uploaded_file_paths:
            await monitoring_service.cleanup_reference_images(uploaded_file_paths)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create monitoring configuration",
            headers={"Content-Type": "application/json"},
        )


async def list_monitoring_configs(
    session: AsyncSession,
    project_id: uuid.UUID,
    enabled: bool | None = None,
    signal_source_id: uuid.UUID | None = None,
    page: int = 1,
    page_size: int = 10,
) -> ListMonitoringConfigsResponse:
    """
    List monitoring configurations for a project.

    Args:
        session: Async database session.
        project_id: Project UUID from query.
        enabled: Optional filter by enabled status.
        signal_source_id: Optional filter by signal source.
        page: Page number (1-based).
        page_size: Items per page.

    Returns:
        ListMonitoringConfigsResponse with paginated results.

    Raises:
        HTTPException: If listing fails.
    """
    try:
        configs, total = await monitoring_service.get_configs(
            session=session,
            project_id=project_id,
            enabled=enabled,
            signal_source_id=signal_source_id,
            page=page,
            page_size=page_size,
        )

        # Build responses asynchronously to avoid blocking event loop
        config_responses = await asyncio.gather(
            *[monitoring_service.build_config_response(config) for config in configs]
        )

        total_pages = math.ceil(total / page_size) if total > 0 else 0

        return ListMonitoringConfigsResponse(
            configs=config_responses,
            total=total,
            total_pages=total_pages,
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
        logger.error(f"Error listing monitoring configs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list monitoring configurations",
            headers={"Content-Type": "application/json"},
        )


async def get_monitoring_config(
    config_id: uuid.UUID,
    session: AsyncSession,
    project_id: uuid.UUID,
) -> MonitoringConfigResponse:
    """
    Get a monitoring configuration by ID.

    Args:
        config_id: Config UUID.
        session: Async database session.
        project_id: Project UUID (for authorization).

    Returns:
        MonitoringConfigResponse.

    Raises:
        HTTPException: If config not found.
    """
    try:
        config = await monitoring_service.get_config(
            session=session,
            project_id=project_id,
            config_id=config_id,
        )

        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Monitoring configuration {config_id} not found",
                headers={"Content-Type": "application/json"},
            )

        return await monitoring_service.build_config_response(config)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting monitoring config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve monitoring configuration",
            headers={"Content-Type": "application/json"},
        )


async def update_monitoring_config(
    config_id: uuid.UUID,
    request: UpdateMonitoringConfigRequest,
    session: AsyncSession,
    project_id: uuid.UUID,
    add_images: list[UploadFile] | None = None,
    add_descriptions: list[str] | None = None,
    add_image_flags: list[str] | None = None,
    remove_image_ids: list[str] | None = None,
    update_image_metadata: dict[str, dict[str, str]] | None = None,
) -> MonitoringConfigResponse:
    """
    Update a monitoring configuration with simple operation-based image management.

    Args:
        config_id: Config UUID.
        request: Update request.
        session: Async database session.
        project_id: Project UUID (for authorization).
        add_images: New image files to add.
        add_descriptions: Descriptions for new images.
        remove_image_ids: List of image UUIDs to remove.
        update_image_metadata: Dict mapping image_id -> metadata updates.
            Supported keys: "description", "flag".

    Returns:
        Updated MonitoringConfigResponse.

    Raises:
        HTTPException: If update fails or config not found.
    """
    # Track uploaded files for potential rollback
    uploaded_file_paths: list[str] = []
    images_to_delete: list[str] = []

    try:
        config, images_to_delete = await monitoring_service.update_config(
            session=session,
            project_id=project_id,
            config_id=config_id,
            request=request,
            add_images=add_images or [],
            add_descriptions=add_descriptions or [],
            add_image_flags=add_image_flags or [],
            remove_image_ids=remove_image_ids or [],
            update_image_metadata=update_image_metadata or {},
        )

        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Monitoring configuration {config_id} not found",
                headers={"Content-Type": "application/json"},
            )

        # Track newly uploaded images for potential rollback
        if add_images and config.rules:
            current_images = config.rules.get("reference_images", [])
            # Get the last N uploaded images (newly added ones)
            num_new = len(add_images)
            if num_new > 0 and len(current_images) >= num_new:
                uploaded_file_paths = [
                    img["url"]
                    for img in current_images[-num_new:]
                    if isinstance(img, dict) and "url" in img
                ]

        # Refresh config to re-establish async session context after asyncio.to_thread()
        await session.refresh(config)

        await session.commit()

        # Clean up old images from S3 AFTER successful database commit
        if images_to_delete:
            await monitoring_service.cleanup_reference_images(images_to_delete)

        # Refresh to reload attributes after commit and avoid greenlet_spawn error
        await session.refresh(config)

        response = await monitoring_service.build_config_response(config)
        logger.info(
            "[update monitoring config] Updated config %s for project %s",
            config_id,
            project_id,
        )
        return response

    except ValueError as e:
        logger.error(
            f"[update monitoring config] Validation error updating config {config_id}: {e}"
        )
        await session.rollback()
        # Clean up any newly uploaded S3 files
        if uploaded_file_paths:
            await monitoring_service.cleanup_reference_images(uploaded_file_paths)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except HTTPException as e:
        logger.error(
            f"[update monitoring config] HTTP error updating config {config_id}: "
            f"status={e.status_code}, detail={e.detail}"
        )
        await session.rollback()
        # Clean up any newly uploaded S3 files
        if uploaded_file_paths:
            await monitoring_service.cleanup_reference_images(uploaded_file_paths)
        raise
    except Exception as e:
        logger.error(
            f"[update monitoring config] Unexpected error updating config {config_id}: {e}",
            exc_info=True,
        )
        await session.rollback()
        # Clean up any newly uploaded S3 files
        if uploaded_file_paths:
            await monitoring_service.cleanup_reference_images(uploaded_file_paths)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update monitoring configuration",
            headers={"Content-Type": "application/json"},
        )


async def delete_monitoring_config(
    config_id: uuid.UUID,
    session: AsyncSession,
    project_id: uuid.UUID,
) -> None:
    """
    Delete a monitoring configuration.

    Args:
        config_id: Config UUID.
        session: Async database session.
        project_id: Project UUID (for authorization).

    Raises:
        HTTPException: If deletion fails or config not found.
    """
    try:
        deleted = await monitoring_service.delete_config(
            session=session,
            project_id=project_id,
            config_id=config_id,
        )

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Monitoring configuration {config_id} not found",
                headers={"Content-Type": "application/json"},
            )

        await session.commit()

    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error(f"Error deleting monitoring config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete monitoring configuration",
            headers={"Content-Type": "application/json"},
        )


async def trigger_monitoring_run(
    config_id: uuid.UUID,
    request: TriggerRunRequest,
    session: AsyncSession,
    project_id: uuid.UUID,
    user_id: str,
) -> TriggerRunResponse:
    """
    Trigger a manual monitoring run.

    Args:
        config_id: Config UUID.
        request: Trigger request with optional S3 details.
        session: Async database session.
        project_id: Project UUID (for authorization).
        user_id: User who triggered the run.

    Returns:
        TriggerRunResponse with run details.

    Raises:
        HTTPException: If trigger fails.
    """
    try:
        run = await monitoring_service.trigger_run(
            session=session,
            project_id=project_id,
            config_id=config_id,
            user_id=user_id,
            s3_bucket=request.s3_bucket,
            s3_key=request.s3_key,
        )

        await session.commit()

        return TriggerRunResponse(
            run_id=run.id,
            monitoring_config_id=run.monitoring_config_id,
            status="processing",
            message="Monitoring run started",
        )

    except ValueError as e:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except Exception as e:
        await session.rollback()
        logger.error(f"Error triggering monitoring run: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to trigger monitoring run",
            headers={"Content-Type": "application/json"},
        )


async def test_monitoring_config(
    config_id: uuid.UUID,
    session: AsyncSession,
    project_id: uuid.UUID,
    test_image: UploadFile | None = None,
) -> TestMonitoringConfigResponse:
    """
    Test a monitoring configuration without saving to database.

    Users can either provide a custom test image or let the system use the latest
    captured image from the signal feed. Runs the monitoring logic and returns the
    prompt sent and analysis result including confidence scores. This allows users
    to preview how the monitoring will analyze images before committing the configuration.

    Test images are NOT saved to S3 - they're passed directly to the LLM for analysis.

    Args:
        config_id: Config UUID.
        session: Async database session.
        project_id: Project UUID (for authorization).
        test_image: Optional uploaded test image. If not provided, uses latest feed image.

    Returns:
        TestMonitoringConfigResponse with prompt, analysis result, and confidence scores.

    Raises:
        HTTPException: If test fails, config not found, or no recent image available.
    """
    test_image_bytes = None

    # If user uploaded a test image, read the bytes (don't save to S3)
    if test_image:
        try:
            logger.info(
                f"[test monitoring config] Reading uploaded test image for config {config_id}"
            )

            if not test_image.filename:
                raise ValueError("Image filename is required.")

            # Read image content (not saved to S3)
            test_image_bytes = await test_image.read()

            logger.info(
                f"[test monitoring config] Test image loaded ({len(test_image_bytes)} bytes)"
            )

        except ValueError as ve:
            logger.error(f"[test monitoring config] Validation error: {ve}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(ve),
            )
        except Exception as e:
            logger.error(f"[test monitoring config] Error reading test image: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to read test image: {str(e)}",
            )

    # Run the test with either uploaded image bytes or feed image
    try:
        result = await monitoring_service.test_monitoring_config(
            session=session,
            project_id=project_id,
            config_id=config_id,
            test_image_bytes=test_image_bytes,
        )

        logger.info(
            "[test monitoring config] Test completed for config %s",
            config_id,
            extra={
                "config_id": str(config_id),
                "project_id": str(project_id),
                "test_image_url": result.get("test_image_url"),
                "test_image_source": result.get("test_image_source"),
                "result": result.get("evaluation_result", {}).get("result"),
                "error_message": result.get("error_message"),
            },
        )

        return TestMonitoringConfigResponse(
            evaluation_result=result["evaluation_result"],
            error_message=result["error_message"],
            prompt_sent=result["prompt_sent"],
            test_image_url=result["test_image_url"],
            test_image_source=result["test_image_source"],
        )

    except ValueError as e:
        logger.error(
            f"[test monitoring config] Validation error testing config {config_id}: {e}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except HTTPException as e:
        logger.error(
            f"[test monitoring config] HTTP error testing config {config_id}: "
            f"status={e.status_code}, detail={e.detail}"
        )
        raise
    except Exception as e:
        logger.error(
            f"[test monitoring config] Unexpected error testing config {config_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to test monitoring configuration",
            headers={"Content-Type": "application/json"},
        )


async def list_monitoring_runs(
    session: AsyncSession,
    monitoring_config_id: uuid.UUID,
    project_id: uuid.UUID,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    result: str | None = None,
) -> ListMonitoringRunsResponse:
    """
    List monitoring runs for a configuration.

    Args:
        session: Async database session.
        monitoring_config_id: Monitoring config UUID from query.
        project_id: Project UUID (for authorization).
        start_date: Optional filter for runs after this date.
        end_date: Optional filter for runs before this date.
        result: Optional filter by result ('pass', 'fail', 'error').

    Returns:
        ListMonitoringRunsResponse with all runs.

    Raises:
        HTTPException: If listing fails.
    """
    try:
        runs = await monitoring_service.get_runs(
            session=session,
            project_id=project_id,
            monitoring_config_id=monitoring_config_id,
            start_date=start_date,
            end_date=end_date,
            result_filter=result,
        )

        # Build responses (using list response builder to avoid S3 calls)
        run_responses = [
            monitoring_service.build_run_list_response(run) for run in runs
        ]

        return ListMonitoringRunsResponse(runs=run_responses)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except Exception as e:
        logger.error(f"Error listing monitoring runs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list monitoring runs",
            headers={"Content-Type": "application/json"},
        )


async def get_monitoring_run(
    run_id: uuid.UUID,
    session: AsyncSession,
    project_id: uuid.UUID,
) -> MonitoringRunResponse:
    """
    Get a monitoring run by ID.

    Args:
        run_id: Run UUID.
        session: Async database session.
        project_id: Project UUID (for authorization).

    Returns:
        MonitoringRunResponse.

    Raises:
        HTTPException: If run not found.
    """
    try:
        run = await monitoring_service.get_run(
            session=session,
            project_id=project_id,
            run_id=run_id,
        )

        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Monitoring run {run_id} not found",
                headers={"Content-Type": "application/json"},
            )

        return monitoring_service.build_run_response(run)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting monitoring run: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve monitoring run",
            headers={"Content-Type": "application/json"},
        )


async def delete_monitoring_run(
    run_id: uuid.UUID,
    session: AsyncSession,
    project_id: uuid.UUID,
) -> dict:
    """
    Delete a monitoring run by ID.

    Args:
        run_id: Run UUID.
        session: Async database session.
        project_id: Project UUID (for authorization).

    Returns:
        Success message.

    Raises:
        HTTPException: If run not found or deletion fails.
    """
    try:
        deleted = await monitoring_service.delete_run(
            session=session,
            project_id=project_id,
            run_id=run_id,
        )

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Monitoring run {run_id} not found",
                headers={"Content-Type": "application/json"},
            )

        await session.commit()

        return {"message": f"Monitoring run {run_id} deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error(f"Error deleting monitoring run: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete monitoring run",
            headers={"Content-Type": "application/json"},
        )


async def batch_delete_monitoring_runs(
    request: BatchDeleteMonitoringRunsRequest,
    session: AsyncSession,
    project_id: uuid.UUID,
) -> BatchDeleteMonitoringRunsResponse:
    """
    Delete multiple monitoring runs by IDs.

    Args:
        request: Batch delete request with list of run IDs.
        session: Async database session.
        project_id: Project UUID (for authorization).

    Returns:
        BatchDeleteMonitoringRunsResponse with deletion results.

    Raises:
        HTTPException: If batch deletion fails.
    """
    try:
        result = await monitoring_service.delete_runs_batch(
            session=session,
            project_id=project_id,
            run_ids=request.run_ids,
        )

        total_requested = len(request.run_ids)
        deleted = result["deleted"]
        not_found = result["not_found"]
        unauthorized = result["unauthorized"]

        # Build summary message
        message_parts = [f"Batch delete completed: {deleted}/{total_requested} deleted"]
        if not_found > 0:
            message_parts.append(f"{not_found} not found")
        if unauthorized > 0:
            message_parts.append(f"{unauthorized} unauthorized")

        await session.commit()

        return BatchDeleteMonitoringRunsResponse(
            deleted=deleted,
            not_found=not_found,
            unauthorized=unauthorized,
            message=", ".join(message_parts),
        )

    except Exception as e:
        await session.rollback()
        logger.error(f"Error batch deleting monitoring runs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to batch delete monitoring runs",
            headers={"Content-Type": "application/json"},
        )
