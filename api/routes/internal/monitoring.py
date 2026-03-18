"""Internal API endpoints for monitoring image processor system.

These endpoints are called by the Monitoring Image Processor Lambda to:
1. Discover which monitoring configs should process an image
2. Create monitoring run records with AI analysis results
"""

import asyncio
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

import db
from db.repositories import (
    AccountRepositoryAsync,
    MonitoringRunRepositoryAsync,
    ProjectRepositoryAsync,
    SignalFeedRepositoryAsync,
    SignalSourceRepositoryAsync,
)
from db.repositories.monitoring_config_repository import MonitoringConfigRepositoryAsync
from db.tables import MonitoringConfig, MonitoringRun
from services import monitoring_service
from services.asset_service import _utils as asset_utils
from utils.dd import statsd
from utils.log import logger

monitoring_router = APIRouter(prefix="/monitoring", tags=["internal-monitoring"])

# TODO: Add API key authentication to restrict access to only:
#   - Lambda: Monitoring Image Processor
# Consider using AWS Signature V4 verification or VPC-only access controls
# to prevent unauthorized external access to these internal endpoints


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


# ============================================================================
# REQUEST/RESPONSE SCHEMAS
# ============================================================================


class InternalMonitoringConfigResponse(BaseModel):
    """Response model for internal monitoring config (simplified for Lambda)."""

    id: UUID
    project_id: UUID
    signal_source_id: UUID
    name: str
    rules: dict
    enabled: bool


class ListInternalMonitoringConfigsResponse(BaseModel):
    """Response for listing monitoring configurations (internal)."""

    configs: list[InternalMonitoringConfigResponse]


class CreateMonitoringRunRequest(BaseModel):
    """Request to create a monitoring run (called by Monitoring Image Processor Lambda)."""

    monitoring_config_id: UUID = Field(..., description="Monitoring config UUID")
    trigger_metadata: dict = Field(
        ...,
        description="Metadata about what triggered this run (SQS message, user, etc.)",
    )
    image_url: str | None = Field(
        None,
        description="S3 key/path of camera image. If provided, LLM analysis will run automatically.",
    )
    evaluation_result: dict | None = Field(
        None,
        description="AI analysis result (result, confidence, finding, etc.). Optional if image_url provided.",
    )
    started_at: datetime | None = Field(
        None, description="When the analysis started. Auto-set if not provided."
    )
    completed_at: datetime | None = Field(
        None, description="When the analysis completed. Auto-set after LLM run."
    )
    error_message: str | None = Field(
        None, description="Error message if analysis failed"
    )


class CreateVideoMonitoringRunRequest(BaseModel):
    """Request to create a video monitoring run (called by Video Processor Lambda)."""

    monitoring_config_id: UUID = Field(..., description="Monitoring config UUID")
    trigger_metadata: dict = Field(
        ...,
        description="Metadata about what triggered this run (SQS message, user, etc.)",
    )
    video_url: str = Field(..., description="S3 key of video file to analyze")


class CreateMonitoringRunResponse(BaseModel):
    """Response after creating a monitoring run."""

    run_id: UUID = Field(..., description="UUID of the created monitoring run")
    monitoring_config_id: UUID
    prompt_sent: dict = Field(
        ...,
        description="The prompt that was sent to the LLM (with system instruction and images structure)",
    )
    analysis_result: dict = Field(
        ..., description="The AI analysis result from the LLM"
    )
    started_at: datetime
    completed_at: datetime | None
    error_message: str | None = Field(
        None, description="Error message if analysis failed or image was invalid"
    )
    skipped: bool = Field(
        default=False,
        description="True if run was skipped (e.g., outside business hours)",
    )


class RecordCaptureRequest(BaseModel):
    """Request to record a camera capture timestamp."""

    signal_source_id: UUID = Field(..., description="Signal source UUID")
    captured_at: datetime | None = Field(
        None,
        description="Timestamp of the capture. Auto-set to current time if not provided.",
    )
    capture_url: str | None = Field(
        None,
        description="URL of the captured image",
    )


class RecordCaptureResponse(BaseModel):
    """Response after recording a capture timestamp."""

    signal_source_id: UUID
    feed_id: UUID | None = Field(None, description="UUID of the signal feed (if found)")
    captured_at: datetime
    success: bool
    last_capture_url: str | None = Field(
        None, description="Presigned URL of the captured image (expires in 24 hours)"
    )


# ============================================================================
# ENDPOINTS
# ============================================================================


@monitoring_router.post("/capture", status_code=status.HTTP_200_OK)
async def record_capture(
    request: RecordCaptureRequest,
    session: AsyncSession = Depends(db.get_db_async),
) -> RecordCaptureResponse:
    """
    Record a camera capture timestamp for a signal source.

    Called by Monitoring Image Processor Lambda BEFORE running any analysis.
    This should be called regardless of whether monitoring configs exist,
    to track when the camera last captured an image.

    The admin console uses this timestamp to determine camera status:
    - Active: last_capture_at within last 3 minutes
    - Inactive: last_capture_at older than 3 minutes or null

    Args:
        request: Capture recording request with signal_source_id
        session: Async database session

    Returns:
        RecordCaptureResponse with capture details

    Raises:
        500: Database error
    """
    try:
        captured_at = request.captured_at or datetime.now(timezone.utc)

        source_repo = SignalSourceRepositoryAsync(session)
        source = await source_repo.get_by_id(request.signal_source_id)

        # Build log metadata with camera details for Datadog alerts
        log_extra = {
            "signal_source_id": str(request.signal_source_id),
            "captured_at": captured_at.isoformat(),
            "event_type": "camera_capture",  # For Datadog filtering
        }

        if source:
            account_repo = AccountRepositoryAsync(session)
            project_repo = ProjectRepositoryAsync(session)

            account = await account_repo.get_account_by_id(source.account_id)
            project = (
                await project_repo.get_project(source.project_id)
                if source.project_id
                else None
            )

            # Extract camera_id from config, fallback to source.id
            camera_id = source.config.get("camera_id") if source.config else None
            camera_name = source.name or "Unnamed Camera"

            # Add camera metadata to logs
            log_extra["camera_id"] = camera_id or str(source.id)
            log_extra["signal_source_uuid"] = str(source.id)  # Keep UUID for reference
            log_extra["camera_name"] = camera_name
            log_extra["account_id"] = str(source.account_id)
            log_extra["account_name"] = account.name if account else "Unknown Account"

            # Only add project info if project_id exists
            if source.project_id:
                log_extra["project_id"] = str(source.project_id)
                log_extra["project_name"] = (
                    project.name if project else "Unknown Project"
                )

        logger.info(
            f"[CameraCapture] Camera capture recorded: {log_extra.get('camera_name', request.signal_source_id)}",
            extra=log_extra,
        )

        feed_repo = SignalFeedRepositoryAsync(session)
        feed = await feed_repo.get_by_source_id(request.signal_source_id)

        if feed:
            await feed_repo.update_last_capture(
                feed.id, captured_at, request.capture_url
            )

            # METRIC: Track camera feed update
            try:
                camera_id = log_extra.get("camera_id", str(request.signal_source_id))
                project_id = log_extra.get("project_id", "unknown")
                statsd.increment(
                    "camera.feed.updated",
                    tags=[
                        f"camera_id:{camera_id}",
                        f"project_id:{project_id}",
                        f"signal_source_id:{request.signal_source_id}",
                    ],
                )
            except Exception as metric_err:
                logger.debug(f"Failed to emit camera.feed.updated metric: {metric_err}")

            # Generate presigned URL if S3 key exists
            presigned_url = None
            if request.capture_url:
                presigned_url = await _generate_presigned_url_safe(request.capture_url)

            logger.info(
                f"[CameraCapture] Updated signal feed {feed.id} last_capture_at",
                extra={
                    "feed_id": str(feed.id),
                    "signal_source_id": str(request.signal_source_id),
                    "last_capture_at": captured_at.isoformat(),
                    "last_capture_url": request.capture_url,
                    "event_type": "camera_capture_success",
                },
            )
            return RecordCaptureResponse(
                signal_source_id=request.signal_source_id,
                feed_id=feed.id,
                captured_at=captured_at,
                success=True,
                last_capture_url=presigned_url,
            )
        else:
            logger.warning(
                f"[Internal API] No signal feed found for signal_source_id={request.signal_source_id}",
                extra={"signal_source_id": str(request.signal_source_id)},
            )
            return RecordCaptureResponse(
                signal_source_id=request.signal_source_id,
                feed_id=None,
                captured_at=captured_at,
                success=False,
                last_capture_url=None,
            )

    except Exception as e:
        logger.error(
            f"[Internal API] Error recording capture for signal_source_id={request.signal_source_id}",
            exc_info=True,
            extra={"signal_source_id": str(request.signal_source_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record capture: {str(e)}",
        ) from e


@monitoring_router.get("/configs")
async def get_monitoring_configs_by_signal_source(
    signal_source_id: UUID = Query(..., description="Signal source UUID"),
    enabled: bool = Query(True, description="Filter by enabled status"),
    session: AsyncSession = Depends(db.get_db_async),
) -> ListInternalMonitoringConfigsResponse:
    """
    Discovery endpoint: Get monitoring configs for a signal source.

    Called by Monitoring Image Processor Lambda when processing an SQS message.
    Returns all enabled monitoring configs associated with the signal source,
    so Lambda can process each config sequentially.

    Args:
        signal_source_id: UUID of the signal source (camera, device, etc.)
        enabled: Filter by enabled status (default: True)
        session: Async database session

    Returns:
        List of monitoring configurations

    Raises:
        500: Database error
    """
    try:
        # Query all configs, then filter by signal_source_id
        # Note: We don't have a direct query by signal_source_id in the repo,
        # so we use a direct query instead
        logger.info(
            f"[Internal API] Discovery request for signal_source_id={signal_source_id}, enabled={enabled}"
        )

        # We need to query across all projects for this signal source
        # Since get_by_project requires project_id, we'll use a direct query
        from sqlalchemy import select

        query = select(MonitoringConfig).filter(
            MonitoringConfig.signal_source_id == signal_source_id
        )

        if enabled is not None:
            query = query.filter(MonitoringConfig.enabled == enabled)

        result = await session.execute(query)
        configs = list(result.scalars().all())

        logger.info(
            f"[Internal API] Found {len(configs)} monitoring config(s) for signal_source_id={signal_source_id}",
            extra={
                "signal_source_id": str(signal_source_id),
                "enabled": enabled,
                "configs_found": len(configs),
            },
        )

        # Convert to response format
        config_responses = [
            InternalMonitoringConfigResponse(
                id=config.id,
                project_id=config.project_id,
                signal_source_id=config.signal_source_id,
                name=config.name,
                rules=config.rules,
                enabled=config.enabled,
            )
            for config in configs
        ]

        return ListInternalMonitoringConfigsResponse(configs=config_responses)

    except Exception as e:
        logger.error(
            f"[Internal API] Error getting monitoring configs for signal_source_id={signal_source_id}",
            exc_info=True,
            extra={"signal_source_id": str(signal_source_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get monitoring configs: {str(e)}",
        ) from e


@monitoring_router.get("/configs/{config_id}")
async def get_monitoring_config_by_id(
    config_id: UUID,
    session: AsyncSession = Depends(db.get_db_async),
) -> InternalMonitoringConfigResponse:
    """
    Get a single monitoring config by ID.

    Called by Monitoring Image Processor Lambda to get config details
    (rules, reference images, etc.) before performing AI analysis.

    Args:
        config_id: UUID of the monitoring configuration
        session: Async database session

    Returns:
        Monitoring configuration details

    Raises:
        404: Config not found
        500: Database error
    """
    try:
        repo = MonitoringConfigRepositoryAsync(session)
        config = await repo.get_by_id(config_id)

        if not config:
            logger.warning(
                f"[Internal API] Monitoring config not found: {config_id}",
                extra={"config_id": str(config_id)},
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Monitoring config {config_id} not found",
            )

        logger.info(
            f"[Internal API] Retrieved monitoring config: {config_id}",
            extra={
                "config_id": str(config_id),
                "project_id": str(config.project_id),
                "signal_source_id": str(config.signal_source_id),
            },
        )

        return InternalMonitoringConfigResponse(
            id=config.id,
            project_id=config.project_id,
            signal_source_id=config.signal_source_id,
            name=config.name,
            rules=config.rules,
            enabled=config.enabled,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[Internal API] Error getting monitoring config: {config_id}",
            exc_info=True,
            extra={"config_id": str(config_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get monitoring config: {str(e)}",
        ) from e


@monitoring_router.post("/runs", status_code=status.HTTP_200_OK)
async def create_monitoring_run(
    request: CreateMonitoringRunRequest,
    session: AsyncSession = Depends(db.get_db_async),
) -> CreateMonitoringRunResponse:
    """
    Run AI analysis on a camera image and save the monitoring run to database.

    Returns the created monitoring run with prompt and analysis results.
    If the monitoring config has a time window configured and the current time
    is outside that window, the run will be skipped and result will be "skipped".

    Called by Monitoring Image Processor Lambda.

    Args:
        request: Monitoring run creation request
        session: Async database session

    Returns:
        Created monitoring run with prompt sent and analysis result

    Raises:
        400: Missing image_url
        404: Monitoring config not found
        500: LLM analysis error or database error
    """
    try:
        # Validate monitoring config exists
        config_repo = MonitoringConfigRepositoryAsync(session)
        config = await config_repo.get_by_id(request.monitoring_config_id)

        if not config:
            logger.warning(
                f"[Internal API] Monitoring config not found: {request.monitoring_config_id}",
                extra={"monitoring_config_id": str(request.monitoring_config_id)},
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Monitoring config {request.monitoring_config_id} not found",
            )

        # Require image_url
        if not request.image_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="image_url is required",
            )

        # Check time window before running LLM analysis
        time_window_config = None
        if config.rules:
            time_window_config = config.rules.get("monitoring_time_window")

        should_skip, skip_reason = await monitoring_service.should_skip_monitoring(
            session=session,
            project_id=config.project_id,
            time_window_config=time_window_config,
        )

        # Log time window check decision
        if time_window_config and time_window_config.get("enabled"):
            logger.info(
                f"[TimeWindow] Route handler check: should_skip={should_skip}, reason={skip_reason}",
                extra={
                    "enforcement_point": "route_handler",
                    "monitoring_config_id": str(request.monitoring_config_id),
                    "should_skip": should_skip,
                    "skip_reason": skip_reason,
                    "time_window_config": time_window_config,
                },
            )

        if should_skip:
            # Create a skipped run record
            run_repo = MonitoringRunRepositoryAsync(session)
            skipped_run = MonitoringRun(
                monitoring_config_id=request.monitoring_config_id,
                trigger_metadata={
                    **request.trigger_metadata,
                    "skipped": True,
                    "skip_reason": skip_reason,
                },
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                evaluation_result={"result": "skipped", "reason": skip_reason},
            )
            created_run = await run_repo.create(skipped_run)

            logger.info(
                f"[Internal API] Monitoring run skipped for config {request.monitoring_config_id}",
                extra={
                    "monitoring_config_id": str(request.monitoring_config_id),
                    "run_id": str(created_run.id),
                    "skip_reason": skip_reason,
                },
            )

            return CreateMonitoringRunResponse(
                run_id=created_run.id,
                monitoring_config_id=request.monitoring_config_id,
                prompt_sent={},
                analysis_result={"result": "skipped", "reason": skip_reason},
                started_at=created_run.started_at,
                completed_at=created_run.completed_at,
                error_message=None,
                skipped=True,
            )

        # Run LLM analysis and create monitoring run
        logger.info(
            f"[Internal API] Running LLM analysis for config {request.monitoring_config_id}",
            extra={
                "monitoring_config_id": str(request.monitoring_config_id),
                "image_url": request.image_url,
            },
        )

        # Create monitoring run with analysis and add to session
        # Note: Transaction commit is handled by get_db_async dependency
        monitoring_run, analysis_details = (
            await monitoring_service.create_monitoring_run_with_analysis(
                session=session,
                monitoring_config_id=request.monitoring_config_id,
                image_url=request.image_url,
                trigger_metadata=request.trigger_metadata,
            )
        )

        analysis_result = analysis_details.get("analysis_result", {})
        result_status = analysis_result.get("result")
        was_skipped = analysis_details.get("skipped", False)

        # Log result
        if was_skipped:
            logger.info(
                f"[Internal API] Monitoring run skipped for config {request.monitoring_config_id}",
                extra={
                    "monitoring_config_id": str(request.monitoring_config_id),
                    "run_id": str(monitoring_run.id),
                    "reason": analysis_result.get("reason"),
                },
            )
        elif result_status == "error":
            logger.warning(
                f"[Internal API] LLM analysis returned error for config {request.monitoring_config_id}",
                extra={
                    "monitoring_config_id": str(request.monitoring_config_id),
                    "run_id": str(monitoring_run.id),
                    "error_message": monitoring_run.error_message,
                },
            )
        else:
            logger.info(
                f"[Internal API] LLM analysis completed for config {request.monitoring_config_id}",
                extra={
                    "monitoring_config_id": str(request.monitoring_config_id),
                    "run_id": str(monitoring_run.id),
                    "result": result_status,
                },
            )

        # Return prompt and analysis result
        return CreateMonitoringRunResponse(
            run_id=monitoring_run.id,
            monitoring_config_id=request.monitoring_config_id,
            prompt_sent=analysis_details.get("prompt_sent", {}),
            analysis_result=analysis_result,
            started_at=monitoring_run.started_at,
            completed_at=monitoring_run.completed_at,
            error_message=monitoring_run.error_message,
            skipped=was_skipped,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[Internal API] Error running LLM analysis for config {request.monitoring_config_id}",
            exc_info=True,
            extra={"monitoring_config_id": str(request.monitoring_config_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to run LLM analysis: {str(e)}",
        ) from e


@monitoring_router.post("/video-runs", status_code=status.HTTP_200_OK)
async def create_video_monitoring_run(
    request: CreateVideoMonitoringRunRequest,
    session: AsyncSession = Depends(db.get_db_async),
) -> CreateMonitoringRunResponse:
    """
    Run AI analysis on video frames and save the monitoring run to database.

    Downloads the video from S3, extracts frames at 10-second intervals,
    and sends them to the configured VLM for analysis against reference images.

    Returns the created monitoring run with prompt and analysis results.
    If the monitoring config has a time window configured and the current time
    is outside that window, the run will be skipped and result will be "skipped".

    Called by Video Processor Lambda.

    Args:
        request: Video monitoring run creation request
        session: Async database session

    Returns:
        Created monitoring run with prompt sent and analysis result

    Raises:
        400: No frames could be extracted from video
        404: Monitoring config not found
        500: Video processing, LLM analysis, or database error
    """
    try:
        # Validate monitoring config exists
        config_repo = MonitoringConfigRepositoryAsync(session)
        config = await config_repo.get_by_id(request.monitoring_config_id)

        if not config:
            logger.warning(
                f"[Internal API] Monitoring config not found: {request.monitoring_config_id}",
                extra={"monitoring_config_id": str(request.monitoring_config_id)},
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Monitoring config {request.monitoring_config_id} not found",
            )

        # Check time window before running LLM analysis
        time_window_config = None
        if config.rules:
            time_window_config = config.rules.get("monitoring_time_window")

        should_skip, skip_reason = await monitoring_service.should_skip_monitoring(
            session=session,
            project_id=config.project_id,
            time_window_config=time_window_config,
        )

        # Log time window check decision
        if time_window_config and time_window_config.get("enabled"):
            logger.info(
                f"[TimeWindow] Route handler check (video): should_skip={should_skip}, reason={skip_reason}",
                extra={
                    "enforcement_point": "route_handler",
                    "monitoring_config_id": str(request.monitoring_config_id),
                    "should_skip": should_skip,
                    "skip_reason": skip_reason,
                    "time_window_config": time_window_config,
                },
            )

        if should_skip:
            # Create a skipped run record
            run_repo = MonitoringRunRepositoryAsync(session)
            skipped_run = MonitoringRun(
                monitoring_config_id=request.monitoring_config_id,
                trigger_metadata={
                    **request.trigger_metadata,
                    "skipped": True,
                    "skip_reason": skip_reason,
                },
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                evaluation_result={"result": "skipped", "reason": skip_reason},
            )
            created_run = await run_repo.create(skipped_run)

            logger.info(
                f"[Internal API] Video monitoring run skipped for config {request.monitoring_config_id}",
                extra={
                    "monitoring_config_id": str(request.monitoring_config_id),
                    "run_id": str(created_run.id),
                    "skip_reason": skip_reason,
                },
            )

            return CreateMonitoringRunResponse(
                run_id=created_run.id,
                monitoring_config_id=request.monitoring_config_id,
                prompt_sent={},
                analysis_result={"result": "skipped", "reason": skip_reason},
                started_at=created_run.started_at,
                completed_at=created_run.completed_at,
                error_message=None,
                skipped=True,
            )

        # Run LLM video analysis and create monitoring run
        logger.info(
            f"[Internal API] Running video LLM analysis for config {request.monitoring_config_id}",
            extra={
                "monitoring_config_id": str(request.monitoring_config_id),
                "video_url": request.video_url,
            },
        )

        monitoring_run, analysis_details = (
            await monitoring_service.create_monitoring_video_run_with_analysis(
                session=session,
                monitoring_config_id=request.monitoring_config_id,
                video_url=request.video_url,
                trigger_metadata=request.trigger_metadata,
            )
        )

        analysis_result = analysis_details.get("analysis_result", {})
        result_status = analysis_result.get("result")
        was_skipped = analysis_details.get("skipped", False)

        # Log result
        if was_skipped:
            logger.info(
                f"[Internal API] Video monitoring run skipped for config {request.monitoring_config_id}",
                extra={
                    "monitoring_config_id": str(request.monitoring_config_id),
                    "run_id": str(monitoring_run.id),
                    "reason": analysis_result.get("reason"),
                },
            )
        elif result_status == "error":
            logger.warning(
                f"[Internal API] Video LLM analysis returned error for config {request.monitoring_config_id}",
                extra={
                    "monitoring_config_id": str(request.monitoring_config_id),
                    "run_id": str(monitoring_run.id),
                    "error_message": monitoring_run.error_message,
                },
            )
        else:
            logger.info(
                f"[Internal API] Video LLM analysis completed for config {request.monitoring_config_id}",
                extra={
                    "monitoring_config_id": str(request.monitoring_config_id),
                    "run_id": str(monitoring_run.id),
                    "result": result_status,
                },
            )

        return CreateMonitoringRunResponse(
            run_id=monitoring_run.id,
            monitoring_config_id=request.monitoring_config_id,
            prompt_sent=analysis_details.get("prompt_sent", {}),
            analysis_result=analysis_result,
            started_at=monitoring_run.started_at,
            completed_at=monitoring_run.completed_at,
            error_message=monitoring_run.error_message,
            skipped=was_skipped,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[Internal API] Error running video LLM analysis for config {request.monitoring_config_id}",
            exc_info=True,
            extra={"monitoring_config_id": str(request.monitoring_config_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to run video LLM analysis: {str(e)}",
        ) from e
