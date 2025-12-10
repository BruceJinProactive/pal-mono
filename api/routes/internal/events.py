"""Internal API endpoints for EventBridge event publishing."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

import db
from api.schemas.events.datasets import (
    CreateDatasetRequest,
    DatasetErrorResponse,
    DatasetGenerationResponse,
)
from db.repositories.agent_repository import AgentRepositoryAsync
from events import DatasetGenerationRequested, SampleEvent, publish_event

events_router = APIRouter(prefix="/events")


@events_router.post("/sample")
async def publish_sample_event():
    """
    Publish a sample event to EventBridge.

    This is for internal validation purposes. It publishes a SampleEvent
    to verify EventBridge integration is working correctly.

    Returns:
        dict: Success status and event details
    """
    event = SampleEvent(
        message="Sample event from internal API",
        timestamp=datetime.now(timezone.utc),
    )

    # publish_event is now async
    success = await publish_event(event)

    return {
        "success": success,
        "event": {
            "detail_type": event.detail_type,
            "message": event.message,
            "timestamp": event.timestamp.isoformat(),
        },
    }


@events_router.post(
    "/datasets",
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        400: {"model": DatasetErrorResponse},
    },
)
async def create_dataset_generation_request(
    request: CreateDatasetRequest,
    session: AsyncSession = Depends(db.get_db_async),
) -> DatasetGenerationResponse:
    """
    Accept dataset generation requests from orchestrator.

    Validates the agent exists, generates a job_id, and publishes a
    DatasetGenerationRequested event to EventBridge for processing.

    Args:
        request: Dataset generation request with agent_id, project, account_name, and actions
        session: Async database session

    Returns:
        DatasetGenerationResponse: 202 response with job_id, status, and actions

    Raises:
        HTTPException 400: Agent details not found
    """
    # TODO: Add database table for job tracking in future
    # This will store job_id, status, actions, timestamps for querying later

    # Validate agent exists
    agent_repository = AgentRepositoryAsync(session)
    agent = await agent_repository.get_agent(request.agent_id)

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Agent details not found for {request.account_name}.",
            headers={"Content-Type": "application/json"},
        )

    # Generate job_id
    job_id = str(uuid.uuid4())

    # Create and publish event
    event = DatasetGenerationRequested(
        job_id=job_id,
        agent_id=request.agent_id,
        project=request.project,
        account_name=request.account_name,
        actions=request.actions.model_dump(),  # Convert Pydantic model to dict
        requested_at=datetime.now(timezone.utc),
    )

    success = await publish_event(event)

    # TODO: Add database table for job tracking in future

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to publish dataset generation event",
            headers={"Content-Type": "application/json"},
        )

    return DatasetGenerationResponse(
        job_id=job_id,
        status="pending",
        actions=request.actions,
    )
