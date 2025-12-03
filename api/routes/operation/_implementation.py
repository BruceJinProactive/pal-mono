import uuid
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from api.routes.admin._utils import UserContext
from api.schemas.admin.camera import (
    GetCameraImageUrlsResponse,
    GetCamerasRequest,
    GetCamerasResponse,
    ImageMetadata,
)
from api.schemas.error.error import ErrorResponse
from services import project_service
from services.vision_service import (
    get_camera_image,
    get_cameras_under_project,
    get_images_by_time_interval,
)
from utils.log import logger


async def health_check(context: UserContext, session: Session):
    """
    Basic health check implementation for operation router.
    """
    return {
        "status": "healthy",
        "router": "operation",
        "user_email": context.email,
    }


async def get_cameras_under_project_handler(
    account_id: str, project_id: str
) -> GetCamerasResponse:
    try:
        logger.info(
            f"Getting cameras for account `{account_id}` and project `{project_id}`"
        )

        if not account_id:
            raise ValueError("Account ID is required.")
        if not project_id:
            raise ValueError("Project ID is required.")

        request = GetCamerasRequest(account_id=account_id, project_id=project_id)
        return get_cameras_under_project(request)

    except ValueError as ve:
        # Log and handle validation errors
        logger.error(f"Error validating request: {ve}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                error_code="VALIDATION_ERROR", error_message=str(ve)
            ).model_dump(),
        )
    except Exception as e:
        # Log the error
        logger.error(f"Error getting cameras: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                error_code="INTERNAL_SERVER_ERROR",
                error_message="An unexpected error occurred while processing the request",
            ).model_dump(),
        )


async def get_camera_image_handler(
    account_id: str, project_id: str, camera_name: str
) -> ImageMetadata:
    try:
        logger.info(
            f"Getting image for account `{account_id}`, project `{project_id}`, "
            f"camera `{camera_name}`"
        )

        if not account_id:
            raise ValueError("Account ID is required.")
        if not project_id:
            raise ValueError("Project ID is required.")
        if not camera_name:
            raise ValueError("Camera name is required.")

        return get_camera_image(account_id, project_id, camera_name)

    except ValueError as ve:
        # Log and handle validation errors
        logger.error(f"Error validating request: {ve}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                error_code="VALIDATION_ERROR", error_message=str(ve)
            ).model_dump(),
        )
    except FileNotFoundError as fnf:
        # Log and handle file not found
        logger.error(f"Image not found: {fnf}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorResponse(
                error_code="IMAGE_NOT_FOUND", error_message=str(fnf)
            ).model_dump(),
        )
    except Exception as e:
        # Log the error
        logger.error(f"Error getting camera image: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                error_code="INTERNAL_SERVER_ERROR",
                error_message="An unexpected error occurred while processing the request",
            ).model_dump(),
        )


async def get_camera_images_by_time_interval_handler(
    context: UserContext,
    session: Session,
    project_id: str,
    camera_name: str,
    start_time: datetime,
    end_time: datetime,
) -> GetCameraImageUrlsResponse:
    """Handle getting camera images by time interval.

    Args:
        context: User context for authentication/authorization
        session: Database session
        project_id: Project UUID string
        camera_name: Camera identifier
        start_time: Start of time range
        end_time: End of time range

    Returns:
        GetCameraImageUrlsResponse with image URLs

    Raises:
        HTTPException: With appropriate status codes for various errors
    """
    try:
        # Verify project exists and user has access
        try:
            project_uuid = uuid.UUID(project_id)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorResponse(
                    error_code="INVALID_PROJECT_ID",
                    error_message=f"Invalid project_id format: {project_id}",
                ).model_dump(),
            ) from e

        project = project_service.get_project(session, project_uuid)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ErrorResponse(
                    error_code="PROJECT_NOT_FOUND",
                    error_message=f"Project {project_id} not found",
                ).model_dump(),
            )

        # Authorization handled by require_project_permission in route decorator

        logger.info(
            f"[Camera] User {context.email} getting images for project `{project_id}`, "
            f"camera `{camera_name}`, time range: {start_time.isoformat()} to {end_time.isoformat()}"
        )

        return get_images_by_time_interval(
            session=session,
            project_id=project_id,
            camera_name=camera_name,
            start_time=start_time,
            end_time=end_time,
        )

    except ValueError as ve:
        # Handle validation errors from vision service
        logger.error(f"Validation error: {ve}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                error_code="VALIDATION_ERROR",
                error_message=str(ve),
            ).model_dump(),
        ) from ve
    except RuntimeError as re:
        # Handle S3 errors (from @handle_s3_errors decorator)
        logger.error(f"S3 error: {re}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                error_code="S3_ERROR",
                error_message=str(re),
            ).model_dump(),
        ) from re
    except Exception as e:
        # Handle unexpected errors
        logger.error(f"Error getting camera images by time interval: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                error_code="INTERNAL_SERVER_ERROR",
                error_message="An unexpected error occurred while processing the request",
            ).model_dump(),
        )
