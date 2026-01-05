"""Internal API endpoints for monitoring image processor system.

These endpoints are called by the Monitoring Image Processor Lambda to:
1. Discover which monitoring configs should process an image
2. Create monitoring run records with AI analysis results
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

import db
from db.repositories.monitoring_config_repository import MonitoringConfigRepositoryAsync
from db.tables import MonitoringConfig
from services import monitoring_service
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


class CreateMonitoringRunResponse(BaseModel):
    """Response after creating a monitoring run."""

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


# ============================================================================
# ENDPOINTS
# ============================================================================


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
    Run AI analysis on a camera image without saving to database.

    Returns both the prompt that was sent to the LLM and the analysis result.
    This is for testing/debugging purposes.

    Called by Monitoring Image Processor Lambda.

    Args:
        request: Monitoring run creation request (only monitoring_config_id and image_url are used)
        session: Async database session

    Returns:
        Prompt sent and analysis result (does not save to database)

    Raises:
        400: Missing image_url
        404: Monitoring config not found
        500: LLM analysis error
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

        # Run LLM analysis
        started_at = datetime.now(timezone.utc)
        logger.info(
            f"[Internal API] Running LLM analysis for config {request.monitoring_config_id}",
            extra={
                "monitoring_config_id": str(request.monitoring_config_id),
                "image_url": request.image_url,
            },
        )

        result = await monitoring_service.generate_monitoring_llm_prompt(
            session=session,
            monitoring_config_id=request.monitoring_config_id,
            image_url=request.image_url,
        )
        completed_at = datetime.now(timezone.utc)

        logger.info(
            f"[Internal API] LLM analysis completed for config {request.monitoring_config_id}",
            extra={
                "monitoring_config_id": str(request.monitoring_config_id),
                "result": result.get("analysis_result", {}).get("result"),
            },
        )

        # Return prompt and analysis result (DO NOT save to database)
        return CreateMonitoringRunResponse(
            monitoring_config_id=request.monitoring_config_id,
            prompt_sent=result.get("prompt_sent", {}),
            analysis_result=result.get("analysis_result", {}),
            started_at=started_at,
            completed_at=completed_at,
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
