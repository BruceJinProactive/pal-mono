"""Internal API endpoints for monitoring image processor system.

These endpoints are called by the Monitoring Image Processor Lambda to:
1. Discover which monitoring configs should process an image
2. Create monitoring run records with AI analysis results
3. Lookup signal sources by camera_id
"""

import uuid
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

import db
from db.repositories.monitoring_config_repository import MonitoringConfigRepositoryAsync
from db.repositories.monitoring_run_repository import MonitoringRunRepositoryAsync
from db.tables import MonitoringConfig, MonitoringRun
from services import signal_source_service
from utils.log import logger

monitoring_router = APIRouter(prefix="/monitoring", tags=["internal-monitoring"])

# TODO: Add API key authentication to restrict access to only:
#   - Lambda: Monitoring Image Processor
# Consider using AWS Signature V4 verification or VPC-only access controls
# to prevent unauthorized external access to these internal endpoints


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
    evaluation_result: dict = Field(
        ..., description="AI analysis result (result, confidence, finding, etc.)"
    )
    started_at: datetime = Field(..., description="When the analysis started")
    completed_at: datetime = Field(..., description="When the analysis completed")
    error_message: str | None = Field(
        None, description="Error message if analysis failed"
    )


class CreateMonitoringRunResponse(BaseModel):
    """Response after creating a monitoring run."""

    id: UUID
    monitoring_config_id: UUID
    started_at: datetime
    completed_at: datetime | None
    success: bool


class SignalSourceIdResponse(BaseModel):
    """Response model for signal source ID lookup."""

    signal_source_id: UUID


# ============================================================================
# ENDPOINTS
# ============================================================================


@monitoring_router.get(
    "/projects/{project_id}/signal-sources/camera",
    response_model=SignalSourceIdResponse,
    responses={
        404: {"description": "Signal source not found"},
        500: {"description": "Internal server error"},
    },
)
async def get_signal_source_by_camera_id(
    project_id: str,
    camera_id: str = Query(
        ..., description="Camera identifier from signal source config"
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> SignalSourceIdResponse:
    """
    Internal endpoint: Get signal source ID by camera_id.

    Called by Lambda functions (e.g., Monitoring Image Processor) to lookup
    signal_source_id using camera_id for further processing.

    Args:
        project_id: UUID of the project
        camera_id: Camera identifier from signal source configuration
        session: Async database session

    Returns:
        SignalSourceIdResponse with signal_source_id

    Raises:
        400: Invalid project_id format
        404: Signal source not found
        500: Database error
    """
    try:
        # Validate and convert project_id to UUID
        try:
            project_uuid = uuid.UUID(project_id)
        except ValueError:
            logger.warning(
                f"[Internal API] Invalid project_id format: {project_id}",
                extra={"project_id": project_id, "camera_id": camera_id},
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid project_id format: {project_id}",
                headers={"Content-Type": "application/json"},
            )

        # Get signal source by camera_id
        source = await signal_source_service.get_source_by_camera_id(
            session=session,
            project_id=project_uuid,
            camera_id=camera_id,
        )

        if not source:
            logger.warning(
                f"[Internal API] Signal source not found for camera_id: {camera_id}",
                extra={"project_id": project_id, "camera_id": camera_id},
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Signal source with camera_id '{camera_id}' not found in project {project_id}",
                headers={"Content-Type": "application/json"},
            )

        logger.info(
            f"[Internal API] Found signal source for camera_id: {camera_id}",
            extra={
                "project_id": project_id,
                "camera_id": camera_id,
                "signal_source_id": str(source.id),
            },
        )

        return SignalSourceIdResponse(signal_source_id=source.id)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "[Internal API] Error getting signal source by camera_id",
            exc_info=True,
            extra={"project_id": project_id, "camera_id": camera_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get signal source: {str(e)}",
            headers={"Content-Type": "application/json"},
        )


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


@monitoring_router.post("/runs", status_code=status.HTTP_201_CREATED)
async def create_monitoring_run(
    request: CreateMonitoringRunRequest,
    session: AsyncSession = Depends(db.get_db_async),
) -> CreateMonitoringRunResponse:
    """
    Create a monitoring run record with AI analysis results.

    Called by Monitoring Image Processor Lambda after performing AI analysis.
    Creates a new monitoring_runs record with the evaluation result,
    trigger metadata, and timestamps.

    Args:
        request: Monitoring run creation request
        session: Async database session

    Returns:
        Created monitoring run details

    Raises:
        404: Monitoring config not found
        500: Database error
    """
    try:
        # Validate monitoring config exists
        config_repo = MonitoringConfigRepositoryAsync(session)
        config = await config_repo.get_by_id(request.monitoring_config_id)

        if not config:
            logger.warning(
                f"[Internal API] Cannot create run: monitoring config not found: {request.monitoring_config_id}",
                extra={"monitoring_config_id": str(request.monitoring_config_id)},
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Monitoring config {request.monitoring_config_id} not found",
            )

        # Create monitoring run
        run_repo = MonitoringRunRepositoryAsync(session)

        new_run = MonitoringRun(
            monitoring_config_id=request.monitoring_config_id,
            trigger_metadata=request.trigger_metadata,
            evaluation_result=request.evaluation_result,
            started_at=request.started_at,
            completed_at=request.completed_at,
            error_message=request.error_message,
        )

        created_run = await run_repo.create(new_run)

        # Extract result for logging
        result = request.evaluation_result.get("result", "unknown")
        confidence = request.evaluation_result.get("confidence")

        logger.info(
            f"[Internal API] Created monitoring run: {created_run.id}",
            extra={
                "run_id": str(created_run.id),
                "monitoring_config_id": str(request.monitoring_config_id),
                "result": result,
                "confidence": confidence,
                "trigger_source": request.trigger_metadata.get("trigger_source"),
            },
        )

        # TODO: If result=fail and alerts configured, trigger alert delivery
        # This will be implemented in future phase

        return CreateMonitoringRunResponse(
            id=created_run.id,
            monitoring_config_id=created_run.monitoring_config_id,
            started_at=created_run.started_at,
            completed_at=created_run.completed_at,
            success=True,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[Internal API] Error creating monitoring run for config {request.monitoring_config_id}",
            exc_info=True,
            extra={"monitoring_config_id": str(request.monitoring_config_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create monitoring run: {str(e)}",
        ) from e
