"""Internal API endpoints for Vision AI observation processing.

These endpoints are called by the Vision Frame Processor Lambda to:
1. Generate entity state observations from camera frames
2. Retrieve the full system prompt for a camera configuration
"""

import asyncio
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

import db
from api.schemas.operations.vision_observation import (
    ConfigurationPromptResponse,
    EntityRoiInfo,
    GenerateObservationResponse,
    TestEventInfo,
    TestGroupSummary,
)
from db.pal_repository import (
    VisionEntityRepository,
    VisionEntityStateDefinitionRepository,
    VisionStateChangeEventRepository,
)
from services import vision_observation_service
from services.asset_service._utils import map_uri_to_s3_url
from utils.log import logger

vision_router = APIRouter(prefix="/vision", tags=["internal-vision"])


# ============================================================================
# ENDPOINTS
# ============================================================================


@vision_router.post("/observations", status_code=status.HTTP_200_OK)
async def create_observation(
    camera_id: UUID = Form(..., description="Camera (signal source) UUID"),
    image_url: str | None = Form(
        default=None,
        description="S3 key/path of camera image. Required if no image file is uploaded.",
    ),
    image: UploadFile | None = File(
        default=None,
        description="Optional image file upload for testing. Takes precedence over image_url.",
    ),
    is_test: bool = Form(
        default=False,
        description="If true, run observation without updating entity state or creating events.",
    ),
    observed_at: datetime | None = Form(
        default=None,
        description="Optional capture timestamp to use for the observation.",
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> GenerateObservationResponse:
    """
    Run LLM analysis on a camera frame and return entity state observations.

    Looks up the camera configuration by camera_id (signal source), then
    loads the LLM provider/model, reference images, retrieves assigned entities
    and their state definitions, builds a structured output schema dynamically,
    and calls the configured LLM to produce observations.

    Supports both Azure OpenAI (gpt-4o) and Google Gemini models based on the
    camera configuration's llm_provider and llm_model fields.

    Image source priority: uploaded file > S3 image_url

    Called by Vision Frame Processor Lambda or manually for testing.

    Args:
        camera_id: UUID of the camera (signal source)
        image_url: S3 key of camera image (optional if image file is uploaded)
        image: Optional uploaded image file for testing
        observed_at: Optional timestamp to use as the observation time
        session: Async database session

    Returns:
        Observation result with entity states, confidence scores, and token usage

    Raises:
        400: Missing both image_url and image file, or config validation errors
        404: Camera or camera configuration not found
        500: LLM analysis error or S3 error
    """
    try:
        image_bytes: bytes | None = None
        if image is not None:
            image_bytes = await image.read()

        if image_bytes is None and not image_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either image_url or image file must be provided",
            )

        observed_at_value = observed_at if isinstance(observed_at, datetime) else None
        is_test_value = is_test if isinstance(is_test, bool) else False

        logger.info(
            "[Internal Vision] Running observation",
            extra={
                "camera_id": str(camera_id),
                "image_url": image_url,
                "has_uploaded_image": image_bytes is not None,
                "observed_at": (
                    observed_at_value.isoformat() if observed_at_value else None
                ),
            },
        )

        result = await vision_observation_service.generate_observation(
            session=session,
            camera_id=camera_id,
            image_url=image_url,
            image_bytes=image_bytes,
            is_test=is_test_value,
            observed_at=observed_at_value,
        )

        if result is None:
            return GenerateObservationResponse(
                camera_id=camera_id,
                observed_at=datetime.now(timezone.utc),
                entity_observations=[],
                raw_llm_response={},
                token_usage={"observed": False, "image_relevant": None},
            )

        logger.info(
            "[Internal Vision] Observation completed",
            extra={
                "camera_id": str(camera_id),
                "entity_count": len(result.entity_observations),
            },
        )

        return result

    except ValueError as e:
        detail = str(e)
        if "not found" in detail:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=detail,
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "[Internal Vision] Error generating observation",
            exc_info=True,
            extra={"camera_id": str(camera_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate observation: {str(e)}",
        ) from e


@vision_router.get(
    "/camera-configs/{config_id}/prompt",
    response_model=ConfigurationPromptResponse,
    status_code=status.HTTP_200_OK,
)
async def get_configuration_prompt(
    config_id: UUID,
    session: AsyncSession = Depends(db.get_db_async),
) -> ConfigurationPromptResponse:
    """
    Get the full system prompt for a camera configuration.

    Builds the complete prompt including entity definitions, ROI hints,
    and output format instructions — exactly what the LLM would receive
    during observation.

    Path Parameters:
    - config_id: UUID of the camera configuration
    """

    result = await vision_observation_service.get_configuration_prompt(
        session=session,
        config_id=config_id,
    )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera configuration {config_id} not found",
        )

    event_repo = VisionStateChangeEventRepository(session)
    test_events = await event_repo.list_test_events_by_config(config_id)

    entity_repo = VisionEntityRepository(session)
    sd_repo = VisionEntityStateDefinitionRepository(session)

    groups: dict[str | None, list[TestEventInfo]] = {}
    for evt in test_events:
        group_key = evt.event_metadata.get("test_group")

        entity = await entity_repo.get_by_id(evt.entity_id)
        entity_name = entity.name if entity else None

        state_def = await sd_repo.get_by_id(evt.new_state_id)
        new_state_name = state_def.name if state_def else None

        frame_url: str | None = None
        if evt.frame_s3_key:
            try:
                frame_url = await asyncio.to_thread(map_uri_to_s3_url, evt.frame_s3_key)
            except Exception:
                frame_url = None

        info = TestEventInfo(
            id=evt.id,
            entity_id=evt.entity_id,
            entity_name=entity_name,
            new_state_id=evt.new_state_id,
            new_state_name=new_state_name,
            observed_at=evt.observed_at,
            confidence=evt.confidence,
            test_group=group_key,
            frame_url=frame_url,
        )
        groups.setdefault(group_key, []).append(info)

    test_group_summaries = [
        TestGroupSummary(test_group=key, events=events)
        for key, events in groups.items()
    ]

    entity_roi_hints = [
        EntityRoiInfo(
            entity_name=entity["name"],
            roi_hint=entity.get("roi_hint"),
        )
        for entity in result.entities_with_states
    ]

    return ConfigurationPromptResponse(
        config_id=config_id,
        llm_provider=result.llm_provider,
        llm_model=result.llm_model,
        system_prompt=result.system_prompt,
        structured_output=result.structured_output,
        entity_roi_hints=entity_roi_hints,
        test_events=test_group_summaries,
    )
