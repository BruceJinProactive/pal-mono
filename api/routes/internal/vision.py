"""Internal API endpoints for Vision AI observation processing.

These endpoints are called by the Vision Frame Processor Lambda to:
1. Generate entity state observations from camera frames
"""

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

import db
from services import vision_observation_service
from utils.log import logger

vision_router = APIRouter(prefix="/vision", tags=["internal-vision"])


# ============================================================================
# ENDPOINTS
# ============================================================================


@vision_router.post("/observations", status_code=status.HTTP_200_OK)
async def create_observation(
    camera_config_id: UUID = Form(..., description="Vision camera configuration UUID"),
    image_url: str | None = Form(
        default=None,
        description="S3 key/path of camera image. Required if no image file is uploaded.",
    ),
    image: UploadFile | None = File(
        default=None,
        description="Optional image file upload for testing. Takes precedence over image_url.",
    ),
    session: AsyncSession = Depends(db.get_db_async),
):
    """
    Run LLM analysis on a camera frame and return entity state observations.

    Loads the camera configuration (prompt, LLM provider/model, reference images),
    retrieves assigned entities and their state definitions, builds a structured
    output schema dynamically, and calls the configured LLM to produce observations.

    Supports both Azure OpenAI (gpt-4o) and Google Gemini models based on the
    camera configuration's llm_provider and llm_model fields.

    Image source priority: uploaded file > S3 image_url

    Called by Vision Frame Processor Lambda or manually for testing.

    Args:
        camera_config_id: UUID of the vision camera configuration
        image_url: S3 key of camera image (optional if image file is uploaded)
        image: Optional uploaded image file for testing
        session: Async database session

    Returns:
        Observation result with entity states, confidence scores, and token usage

    Raises:
        400: Missing both image_url and image file, or config validation errors
        404: Camera configuration not found
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

        logger.info(
            "[Internal Vision] Running observation",
            extra={
                "camera_config_id": str(camera_config_id),
                "image_url": image_url,
                "has_uploaded_image": image_bytes is not None,
            },
        )

        result = await vision_observation_service.generate_observation(
            session=session,
            camera_config_id=camera_config_id,
            image_url=image_url,
            image_bytes=image_bytes,
        )

        logger.info(
            "[Internal Vision] Observation completed",
            extra={
                "camera_config_id": str(camera_config_id),
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
            extra={"camera_config_id": str(camera_config_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate observation: {str(e)}",
        ) from e
