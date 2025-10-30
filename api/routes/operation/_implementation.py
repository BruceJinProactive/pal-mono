from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from api.routes.admin._utils import UserContext
from api.schemas.admin.camera import GetCamerasRequest, GetCamerasResponse
from api.schemas.error.error import ErrorResponse
from services.vision_service import get_cameras_under_project
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
