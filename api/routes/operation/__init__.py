import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

import db
from api.routes.admin._auth import authenticate_user
from api.routes.asset import _implementation as asset_implementation
from api.routes.endpoints import endpoints
from api.schemas.admin.camera import (
    GetCameraImageUrlsResponse,
    GetCamerasResponse,
    ImageMetadata,
)
from api.schemas.asset.asset import AssetResponse
from api.schemas.error.error import ErrorResponse
from api.schemas.operations.monitoring import (
    BatchDeleteMonitoringRunsRequest,
    BatchDeleteMonitoringRunsResponse,
    CreateMonitoringConfigRequest,
    ListMonitoringConfigsResponse,
    ListMonitoringRunsResponse,
    MonitoringConfigResponse,
    MonitoringRunResponse,
    MonitoringTimeWindow,
    RerunMonitoringRunResponse,
    TestMonitoringConfigResponse,
    TriggerRunRequest,
    TriggerRunResponse,
    UpdateMonitoringConfigRequest,
)
from api.schemas.operations.routine import (
    CreateRoutineItemRequest,
    CreateRoutineRequest,
    CreateScheduleRequest,
    ExecutionDetailResponse,
    ItemResponseWithItemResponse,
    ListExecutionsResponse,
    ListPendingReviewResponse,
    ListRoutinesResponse,
    ListSchedulesResponse,
    RejectSubmissionRequest,
    RoutineDetailResponse,
    RoutineItemResponse,
    RoutineResponse,
    ScheduleResponse,
    SubmissionDetailResponse,
    SubmissionResponse,
    UpdateReferenceImagesRequest,
    UpdateRoutineItemRequest,
    UpdateRoutineRequest,
    UpdateScheduleRequest,
)
from api.schemas.operations.signal_source import (
    CreateSignalSourceRequest,
    ListSignalSourcesResponse,
    SignalSourceIdResponse,
    SignalSourceResponse,
    UpdateSignalSourceRequest,
)
from api.schemas.operations.vision_camera_configuration import (
    AssignEntityRequest,
    CameraConfigResponse,
    CameraEntityResponse,
    CreateCameraConfigRequest,
    ListCameraConfigsResponse,
    ListCameraEntitiesResponse,
    UpdateCameraConfigRequest,
    UpdateCameraEntityRequest,
)
from api.schemas.operations.vision_entity import (
    CreateEntityRequest,
    CreateEntityTypeRequest,
    CreateStateDefinitionRequest,
    EntityResponse,
    EntityTypeResponse,
    ListEntitiesResponse,
    ListEntityTypesResponse,
    ListStateDefinitionsResponse,
    StateDefinitionResponse,
    UpdateEntityRequest,
    UpdateEntityStateRequest,
    UpdateEntityTypeRequest,
    UpdateStateDefinitionRequest,
)
from api.schemas.operations.vision_rule import (
    CreateVisionRuleRequest,
    ListVisionRulesResponse,
    UpdateVisionRuleRequest,
    VisionRuleResponse,
)
from api.schemas.operations.vision_rule_event import (
    ListVisionRuleEventsResponse,
    VisionRuleEventResponse,
)
from api.schemas.operations.vision_state_change_event import (
    CreateStateChangeEventRequest,
    ListStateChangeEventsResponse,
    StateChangeEventResponse,
    UpdateStateChangeEventRequest,
)
from db.pal_repository.project import ProjectRepository
from db.tables.types import ExecutionStatus
from services import signal_source_service
from services.auth_service.authorization import check_permission
from services.auth_service.dependencies import (
    require_account_permission,
    require_execution_permission,
    require_project_permission,
    require_routine_permission,
    require_submission_permission,
)
from services.auth_types import UserContext
from utils.log import logger

from . import (
    _implementation,
    _monitoring,
    _photo_upload,
    _routines,
    _signal_sources,
    _video_upload,
    _vision_camera_configs,
    _vision_entities,
    _vision_rule_events,
    _vision_rules,
    _vision_state_change_events,
)

operation_router = APIRouter(prefix=endpoints.OPERATION, tags=["Operation"])


@operation_router.post(
    "/accounts/{account_id}/projects/{project_id}/cameras/{camera_id}/upload",
    response_model=AssetResponse,
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def upload_camera_image(
    account_id: str,
    project_id: str,
    camera_id: str,
    image: UploadFile = File(...),
    session: AsyncSession = Depends(db.get_db_async),
) -> AssetResponse:
    """
    Upload a camera image to S3 without authentication.

    This endpoint is designed for camera devices to upload images directly.
    The camera_id is validated against registered signal sources if possible,
    but upload proceeds regardless to ensure device reliability.

    Path Parameters:
    - account_id: The account ID
    - project_id: The project ID
    - camera_id: The camera identifier (from signal source config)

    Request body (multipart/form-data):
    - image: The image file to upload

    Returns:
    - url: S3 URL of the uploaded image
    """
    # Validate camera exists
    try:
        source = await signal_source_service.get_source_by_camera_id(
            session=session,
            project_id=uuid.UUID(project_id),
            camera_id=camera_id,
        )
    except Exception as e:
        logger.error(
            "Failed to lookup camera for upload",
            extra={
                "camera_id": camera_id,
                "project_id": project_id,
                "account_id": account_id,
                "error": str(e),
            },
        )
        return AssetResponse(url="")

    if not source:
        logger.warning(
            "Camera not found for upload",
            extra={
                "camera_id": camera_id,
                "project_id": project_id,
                "account_id": account_id,
            },
        )
        return AssetResponse(url="")

    path = f"security/cameras/{account_id}/{project_id}/{camera_id}"
    return await asset_implementation.upload_asset(image, path, {})


@operation_router.post(
    "/accounts/{account_id}/projects/{project_id}/cameras/{camera_id}/upload-video",
    response_model=AssetResponse,
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def upload_camera_video(
    account_id: str,
    project_id: str,
    camera_id: str,
    video: UploadFile = File(...),
    session: AsyncSession = Depends(db.get_db_async),
) -> AssetResponse:
    """
    Upload a video segment from a camera to S3 using streaming.

    This endpoint is designed for camera recording systems to upload video
    segments directly. It uses streaming upload to handle large video files
    efficiently without loading the entire file into memory.

    Path Parameters:
    - account_id: The account ID
    - project_id: The project ID
    - camera_id: The camera identifier (from signal source config)

    Request body (multipart/form-data):
    - video: The video file to upload (.mkv, .mp4, .mov, .avi, .webm)

    Returns:
    - url: S3 key of the uploaded video

    The video will be stored at:
    security/cameras/{account_id}/{project_id}/{camera_id}/videos/{date}/{filename}
    """
    return await _video_upload.upload_camera_video(
        account_id=account_id,
        project_id=project_id,
        camera_id=camera_id,
        video=video,
        session=session,
    )


@operation_router.post(
    "/accounts/{account_id}/projects/{project_id}/cameras/{camera_id}/upload-photo",
    response_model=AssetResponse,
    responses={
        400: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def upload_camera_photo(
    account_id: str,
    project_id: str,
    camera_id: str,
    photo: UploadFile = File(...),
    session: AsyncSession = Depends(db.get_db_async),
) -> AssetResponse:
    """
    Upload a photo snapshot from a camera to the images S3 bucket.

    This endpoint is designed for camera snapshot systems that capture
    JPEG frames at regular intervals (e.g., every 15 seconds).

    Path Parameters:
    - account_id: The account ID
    - project_id: The project ID
    - camera_id: The camera identifier (from signal source config)

    Request body (multipart/form-data):
    - photo: The image file to upload (.jpg, .jpeg, .png)

    Returns:
    - url: S3 key of the uploaded photo

    The photo will be stored at:
    security/cameras/{account_id}/{project_id}/{camera_name}/images/{date}/{timestamp}-{uuid8}{ext}
    """
    return await _photo_upload.upload_camera_photo(
        account_id=account_id,
        project_id=project_id,
        camera_id=camera_id,
        photo=photo,
        session=session,
    )


@operation_router.get("/health")
async def health_check(
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
):
    """
    Health check endpoint for operation router.
    """
    return await _implementation.health_check(context, session)


@operation_router.get(
    "/accounts/{account_id}/projects/{project_id}/cameras",
    response_model=GetCamerasResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def get_cameras_under_project(
    account_id: str,
    project_id: str,
    context: UserContext = Depends(authenticate_user),
) -> GetCamerasResponse:
    """
    Get all cameras under a specific project within an account.

    Path Parameters:
    - account_id: The account ID
    - project_id: The project ID

    Returns:
    - cameras: List of camera names/IDs under the project
    """
    return await _implementation.get_cameras_under_project_handler(
        account_id, project_id
    )


@operation_router.get(
    "/accounts/{account_id}/projects/{project_id}/cameras/{camera_name}/image",
    response_model=ImageMetadata,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_camera_image(
    account_id: str,
    project_id: str,
    camera_name: str,
    context: UserContext = Depends(authenticate_user),
) -> ImageMetadata:
    """
    Get the single camera image named {camera_name}.png.

    Path Parameters:
    - account_id: The account ID
    - project_id: The project ID
    - camera_name: The camera name/ID

    Returns:
    - ImageMetadata: Image metadata including filename, URL, last_modified, and size
    """
    return await _implementation.get_camera_image_handler(
        account_id, project_id, camera_name
    )


@operation_router.get(
    "/projects/{project_id}/cameras/{camera_name}/images",
    response_model=GetCameraImageUrlsResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_camera_images_by_time_interval(
    project_id: str,
    camera_name: str,
    start_time: datetime = Query(
        ...,
        description="Start time in ISO 8601 format (e.g., 2025-11-03T14:00:00Z)",
    ),
    end_time: datetime = Query(
        ...,
        description="End time in ISO 8601 format (e.g., 2025-11-03T18:00:00Z)",
    ),
    context: UserContext = Depends(
        require_project_permission("project.read", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> GetCameraImageUrlsResponse:
    """
    Get camera images within a time range (< 24 hours recommended).

    This endpoint retrieves presigned S3 URLs for camera images captured within
    the specified time range. Uses optimized S3 prefix filtering for fast queries.

    Path Parameters:
    - project_id: The project UUID
    - camera_name: The camera identifier

    Query Parameters:
    - start_time (required): Start of time range in ISO 8601 format (UTC recommended)
    - end_time (required): End of time range in ISO 8601 format (UTC recommended)

    Returns:
    - urls: List of presigned S3 URLs (valid for 1 hour)

    Notes:
    - Time range must be less than 24 hours
    - Image filenames must be in format: YYYYMMDD_HHMMSS.{png|jpeg|jpg}
    - Results are sorted chronologically (oldest first)
    - Account ID is automatically determined from project ID

    Example:
    GET /projects/123e4567-e89b-12d3-a456-426614174000/cameras/front_entrance/images?start_time=2025-11-04T22:00:00Z&end_time=2025-11-05T02:00:00Z
    """
    return await _implementation.get_camera_images_by_time_interval_handler(
        context=context,
        session=session,
        project_id=project_id,
        camera_name=camera_name,
        start_time=start_time,
        end_time=end_time,
    )


"""
---------- Signal Source Endpoints ----------
---------------------------------------------
"""


@operation_router.post(
    "/projects/{project_id}/signal-sources",
    response_model=SignalSourceResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def create_signal_source(
    project_id: uuid.UUID,
    request: CreateSignalSourceRequest,
    context: UserContext = Depends(
        require_project_permission("project.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> SignalSourceResponse:
    """
    Create a new signal source (camera device) for a project.

    Signal sources represent data providers (cameras in V1) that can be
    monitored. Each source automatically gets an associated feed for
    capturing data.

    Path Parameters:
    - project_id: UUID of the project

    Request Body:
    - name (required): Name of the signal source
    - config (required): Type-specific configuration
    - description (optional): Description of the source

    Returns:
    - SignalSourceResponse with the created source details
    """
    _ = context  # Used by require_project_permission
    return await _signal_sources.create_signal_source(
        request=request,
        session=session,
        project_id=project_id,
    )


@operation_router.get(
    "/projects/{project_id}/signal-sources",
    response_model=ListSignalSourcesResponse,
    responses={
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def list_signal_sources(
    project_id: uuid.UUID,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    context: UserContext = Depends(
        require_project_permission("project.read", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> ListSignalSourcesResponse:
    """
    List signal sources for a project.

    Path Parameters:
    - project_id: UUID of the project

    Query Parameters:
    - page (optional, default: 1): Page number
    - page_size (optional, default: 20): Items per page

    Returns:
    - ListSignalSourcesResponse with paginated results
    """
    _ = context  # Used by require_project_permission
    return await _signal_sources.list_signal_sources(
        session=session,
        project_id=project_id,
        page=page,
        page_size=page_size,
    )


@operation_router.get(
    "/projects/{project_id}/signal-sources/camera",
    response_model=SignalSourceIdResponse,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_signal_source_by_camera_id(
    project_id: uuid.UUID,
    camera_id: str = Query(
        ..., description="Camera identifier from signal source config"
    ),
    context: UserContext = Depends(
        require_project_permission("project.read", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> SignalSourceIdResponse:
    """
    Lookup signal source ID by camera identifier.

    This endpoint allows you to find a signal source using its camera_id
    instead of the signal_source_id UUID.

    Path Parameters:
    - project_id: UUID of the project

    Query Parameters:
    - camera_id (required): Camera identifier from signal source configuration

    Returns:
    - SignalSourceIdResponse with signal_source_id

    Example:
    - GET /projects/{project_id}/signal-sources/camera?camera_id=camera123
    """
    _ = context  # Used by require_project_permission
    return await _signal_sources.get_signal_source_by_camera_id(
        project_id=project_id,
        camera_id=camera_id,
        session=session,
    )


@operation_router.get(
    "/projects/{project_id}/signal-sources/{source_id}",
    response_model=SignalSourceResponse,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_signal_source(
    project_id: uuid.UUID,
    source_id: uuid.UUID,
    context: UserContext = Depends(
        require_project_permission("project.read", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> SignalSourceResponse:
    """
    Get a signal source by ID.

    Path Parameters:
    - project_id: UUID of the project
    - source_id: UUID of the signal source

    Returns:
    - SignalSourceResponse with source details
    """
    _ = context  # Used by require_project_permission
    return await _signal_sources.get_signal_source(
        source_id=source_id,
        session=session,
        project_id=project_id,
    )


@operation_router.patch(
    "/projects/{project_id}/signal-sources/{source_id}",
    response_model=SignalSourceResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def update_signal_source(
    project_id: uuid.UUID,
    source_id: uuid.UUID,
    request: UpdateSignalSourceRequest,
    context: UserContext = Depends(
        require_project_permission("project.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> SignalSourceResponse:
    """
    Update a signal source.

    Cannot change signal_type or project_id.

    Path Parameters:
    - project_id: UUID of the project
    - source_id: UUID of the signal source

    Request Body (all optional):
    - name: New name
    - config: Updated configuration
    - description: Updated description
    - status: Updated status (active, inactive, error)

    Returns:
    - SignalSourceResponse with updated source details
    """
    _ = context  # Used by require_project_permission
    return await _signal_sources.update_signal_source(
        source_id=source_id,
        request=request,
        session=session,
        project_id=project_id,
    )


@operation_router.delete(
    "/projects/{project_id}/signal-sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def delete_signal_source(
    project_id: uuid.UUID,
    source_id: uuid.UUID,
    context: UserContext = Depends(
        require_project_permission("project.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> None:
    """
    Delete a signal source and its associated feed.

    Path Parameters:
    - project_id: UUID of the project
    - source_id: UUID of the signal source
    """
    _ = context  # Used by require_project_permission
    return await _signal_sources.delete_signal_source(
        source_id=source_id,
        session=session,
        project_id=project_id,
    )


# ==============================================================================
# VISION ENTITY TYPE ENDPOINTS
# ==============================================================================


@operation_router.post(
    "/accounts/{account_name}/entity-types",
    status_code=status.HTTP_201_CREATED,
    response_model=EntityTypeResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def create_entity_type(
    account_name: str,
    request: CreateEntityTypeRequest,
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> EntityTypeResponse:
    """
    Create a new vision entity type for an account.

    Entity types define categories of trackable objects (e.g., "table", "employee").

    Path Parameters:
    - account_name: Name of the account
    """
    _ = context
    return await _vision_entities.create_entity_type(
        session=session,
        account_name=account_name,
        request=request,
    )


@operation_router.get(
    "/accounts/{account_name}/entity-types",
    response_model=ListEntityTypesResponse,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def list_entity_types(
    account_name: str,
    is_active: bool | None = Query(default=None, description="Filter by active status"),
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> ListEntityTypesResponse:
    """
    List all entity types for an account.

    Path Parameters:
    - account_name: Name of the account

    Query Parameters:
    - is_active (optional): Filter by active status
    """
    _ = context
    return await _vision_entities.list_entity_types(
        session=session,
        account_name=account_name,
        is_active=is_active,
    )


@operation_router.get(
    "/accounts/{account_name}/entity-types/{entity_type_id}",
    response_model=EntityTypeResponse,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_entity_type(
    account_name: str,
    entity_type_id: uuid.UUID,
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> EntityTypeResponse:
    """
    Get an entity type by ID.

    Path Parameters:
    - account_name: Name of the account
    - entity_type_id: UUID of the entity type
    """
    _ = context
    return await _vision_entities.get_entity_type(
        session=session,
        account_name=account_name,
        entity_type_id=entity_type_id,
    )


@operation_router.patch(
    "/accounts/{account_name}/entity-types/{entity_type_id}",
    response_model=EntityTypeResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def update_entity_type(
    account_name: str,
    entity_type_id: uuid.UUID,
    request: UpdateEntityTypeRequest,
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> EntityTypeResponse:
    """
    Update an entity type.

    Path Parameters:
    - account_name: Name of the account
    - entity_type_id: UUID of the entity type
    """
    _ = context
    return await _vision_entities.update_entity_type(
        session=session,
        account_name=account_name,
        entity_type_id=entity_type_id,
        request=request,
    )


@operation_router.delete(
    "/accounts/{account_name}/entity-types/{entity_type_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def delete_entity_type(
    account_name: str,
    entity_type_id: uuid.UUID,
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> None:
    """
    Delete an entity type.

    Path Parameters:
    - account_name: Name of the account
    - entity_type_id: UUID of the entity type
    """
    _ = context
    return await _vision_entities.delete_entity_type(
        session=session,
        account_name=account_name,
        entity_type_id=entity_type_id,
    )


# ==============================================================================
# VISION ENTITY STATE DEFINITION ENDPOINTS
# ==============================================================================


@operation_router.post(
    "/accounts/{account_name}/entity-types/{entity_type_id}/state-definitions",
    status_code=status.HTTP_201_CREATED,
    response_model=StateDefinitionResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def create_state_definition(
    account_name: str,
    entity_type_id: uuid.UUID,
    request: CreateStateDefinitionRequest,
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> StateDefinitionResponse:
    """
    Create a new state definition for an entity type.

    State definitions describe the possible states an entity can be in
    (e.g., "dirty", "clean", "occupied").

    Path Parameters:
    - account_name: Name of the account
    - entity_type_id: UUID of the entity type
    """
    _ = context
    return await _vision_entities.create_state_definition(
        session=session,
        account_name=account_name,
        entity_type_id=entity_type_id,
        request=request,
    )


@operation_router.get(
    "/accounts/{account_name}/entity-types/{entity_type_id}/state-definitions",
    response_model=ListStateDefinitionsResponse,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def list_state_definitions(
    account_name: str,
    entity_type_id: uuid.UUID,
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> ListStateDefinitionsResponse:
    """
    List all state definitions for an entity type.

    Path Parameters:
    - account_name: Name of the account
    - entity_type_id: UUID of the entity type
    """
    _ = context
    return await _vision_entities.list_state_definitions(
        session=session,
        account_name=account_name,
        entity_type_id=entity_type_id,
    )


@operation_router.patch(
    "/accounts/{account_name}/entity-types/{entity_type_id}/state-definitions/{state_definition_id}",
    response_model=StateDefinitionResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def update_state_definition(
    account_name: str,
    entity_type_id: uuid.UUID,
    state_definition_id: uuid.UUID,
    request: UpdateStateDefinitionRequest,
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> StateDefinitionResponse:
    """
    Update a state definition.

    Path Parameters:
    - account_name: Name of the account
    - entity_type_id: UUID of the entity type
    - state_definition_id: UUID of the state definition
    """
    _ = context
    return await _vision_entities.update_state_definition(
        session=session,
        account_name=account_name,
        entity_type_id=entity_type_id,
        state_definition_id=state_definition_id,
        request=request,
    )


@operation_router.delete(
    "/accounts/{account_name}/entity-types/{entity_type_id}/state-definitions/{state_definition_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def delete_state_definition(
    account_name: str,
    entity_type_id: uuid.UUID,
    state_definition_id: uuid.UUID,
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> None:
    """
    Delete a state definition.

    Returns 400 if the state is currently in use by any entity.

    Path Parameters:
    - account_name: Name of the account
    - entity_type_id: UUID of the entity type
    - state_definition_id: UUID of the state definition
    """
    _ = context
    return await _vision_entities.delete_state_definition(
        session=session,
        account_name=account_name,
        entity_type_id=entity_type_id,
        state_definition_id=state_definition_id,
    )


# ==============================================================================
# VISION ENTITY ENDPOINTS (project-scoped)
# ==============================================================================


@operation_router.post(
    "/projects/{project_id}/entities",
    status_code=status.HTTP_201_CREATED,
    response_model=EntityResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def create_entity(
    project_id: uuid.UUID,
    request: CreateEntityRequest,
    context: UserContext = Depends(
        require_project_permission("project.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> EntityResponse:
    """
    Create a new vision entity under a project.

    Automatically assigns the default state for the entity type if one exists.

    Path Parameters:
    - project_id: UUID of the project
    """
    _ = context
    return await _vision_entities.create_entity(
        session=session,
        project_id=project_id,
        request=request,
    )


@operation_router.get(
    "/projects/{project_id}/entities",
    response_model=ListEntitiesResponse,
    responses={
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def list_entities(
    project_id: uuid.UUID,
    entity_type_id: uuid.UUID | None = Query(
        default=None, description="Filter by entity type"
    ),
    current_state_id: uuid.UUID | None = Query(
        default=None, description="Filter by current state"
    ),
    context: UserContext = Depends(
        require_project_permission("project.read", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> ListEntitiesResponse:
    """
    List entities for a project.

    Path Parameters:
    - project_id: UUID of the project

    Query Parameters:
    - entity_type_id (optional): Filter by entity type
    - current_state_id (optional): Filter by current state
    """
    _ = context
    return await _vision_entities.list_entities(
        session=session,
        project_id=project_id,
        entity_type_id=entity_type_id,
        current_state_id=current_state_id,
    )


@operation_router.get(
    "/projects/{project_id}/entities/{entity_id}",
    response_model=EntityResponse,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_entity(
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
    context: UserContext = Depends(
        require_project_permission("project.read", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> EntityResponse:
    """
    Get a single entity with its current state.

    Path Parameters:
    - project_id: UUID of the project
    - entity_id: UUID of the entity
    """
    _ = context
    return await _vision_entities.get_entity(
        session=session,
        project_id=project_id,
        entity_id=entity_id,
    )


@operation_router.patch(
    "/projects/{project_id}/entities/{entity_id}",
    response_model=EntityResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def update_entity(
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
    request: UpdateEntityRequest,
    context: UserContext = Depends(
        require_project_permission("project.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> EntityResponse:
    """
    Update an entity's name, metadata, or active status.

    Path Parameters:
    - project_id: UUID of the project
    - entity_id: UUID of the entity
    """
    _ = context
    return await _vision_entities.update_entity(
        session=session,
        project_id=project_id,
        entity_id=entity_id,
        request=request,
    )


@operation_router.put(
    "/projects/{project_id}/entities/{entity_id}/state",
    response_model=EntityResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def update_entity_state(
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
    request: UpdateEntityStateRequest,
    context: UserContext = Depends(
        require_project_permission("project.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> EntityResponse:
    """
    Transition an entity to a new state.

    Sets current_state_id and current_state_since. The target state must
    belong to the entity's type.

    Path Parameters:
    - project_id: UUID of the project
    - entity_id: UUID of the entity
    """
    _ = context
    return await _vision_entities.update_entity_state(
        session=session,
        project_id=project_id,
        entity_id=entity_id,
        request=request,
    )


@operation_router.delete(
    "/projects/{project_id}/entities/{entity_id}/states/{definition_type}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def delete_entity_state(
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
    definition_type: str,
    context: UserContext = Depends(
        require_project_permission("project.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> None:
    """
    Remove one current state type from an entity.

    Path Parameters:
    - project_id: UUID of the project
    - entity_id: UUID of the entity
    - definition_type: State definition type to remove, such as cleanliness
    """
    _ = context
    await _vision_entities.delete_entity_state(
        session=session,
        project_id=project_id,
        entity_id=entity_id,
        definition_type=definition_type,
    )


@operation_router.delete(
    "/projects/{project_id}/entities/{entity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def delete_entity(
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
    context: UserContext = Depends(
        require_project_permission("project.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> None:
    """
    Delete an entity.

    Path Parameters:
    - project_id: UUID of the project
    - entity_id: UUID of the entity
    """
    _ = context
    return await _vision_entities.delete_entity(
        session=session,
        project_id=project_id,
        entity_id=entity_id,
    )


# ==============================================================================
# VISION CAMERA CONFIGURATION ENDPOINTS
# ==============================================================================


@operation_router.post(
    "/projects/{project_id}/camera-configs",
    status_code=status.HTTP_201_CREATED,
    response_model=CameraConfigResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def create_camera_config(
    project_id: uuid.UUID,
    signal_source_id: uuid.UUID = Form(...),
    name: str = Form(...),
    llm_prompt: str = Form(...),
    llm_provider: str = Form(default="azure"),
    llm_model: str = Form(default="gpt-4o"),
    processing_interval_seconds: int = Form(default=15),
    enabled: bool = Form(default=True),
    reference_images: list[UploadFile] = File(default=[]),
    reference_image_descriptions: list[str] = Form(default=[]),
    context: UserContext = Depends(
        require_project_permission("project.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> CameraConfigResponse:
    """
    Create a vision camera configuration for a signal source.

    Each signal source can have at most one camera configuration that controls
    how the LLM processes captured frames. Supports optional reference image uploads.

    Path Parameters:
    - project_id: UUID of the project
    """
    _ = context

    if len(reference_images) != len(reference_image_descriptions):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Number of images ({len(reference_images)}) must match number of descriptions ({len(reference_image_descriptions)})",
            headers={"Content-Type": "application/json"},
        )

    request = CreateCameraConfigRequest(
        signal_source_id=signal_source_id,
        name=name,
        llm_prompt=llm_prompt,
        llm_provider=llm_provider,
        llm_model=llm_model,
        processing_interval_seconds=processing_interval_seconds,
        enabled=enabled,
    )

    return await _vision_camera_configs.create_camera_config(
        session=session,
        project_id=project_id,
        request=request,
        reference_images=reference_images,
        reference_image_descriptions=reference_image_descriptions,
    )


@operation_router.get(
    "/projects/{project_id}/camera-configs",
    response_model=ListCameraConfigsResponse,
    responses={
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def list_camera_configs(
    project_id: uuid.UUID,
    context: UserContext = Depends(
        require_project_permission("project.read", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> ListCameraConfigsResponse:
    """
    List all vision camera configurations for a project.

    Path Parameters:
    - project_id: UUID of the project
    """
    _ = context
    return await _vision_camera_configs.list_camera_configs(
        session=session,
        project_id=project_id,
    )


@operation_router.get(
    "/projects/{project_id}/camera-configs/by-source/{signal_source_id}",
    response_model=CameraConfigResponse,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_camera_config_by_source(
    project_id: uuid.UUID,
    signal_source_id: uuid.UUID,
    context: UserContext = Depends(
        require_project_permission("project.read", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> CameraConfigResponse:
    """
    Get a vision camera configuration by its signal source ID.

    Path Parameters:
    - project_id: UUID of the project
    - signal_source_id: UUID of the signal source
    """
    _ = context
    return await _vision_camera_configs.get_camera_config_by_source(
        session=session,
        project_id=project_id,
        signal_source_id=signal_source_id,
    )


@operation_router.get(
    "/projects/{project_id}/camera-configs/{config_id}",
    response_model=CameraConfigResponse,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_camera_config(
    project_id: uuid.UUID,
    config_id: uuid.UUID,
    context: UserContext = Depends(
        require_project_permission("project.read", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> CameraConfigResponse:
    """
    Get a vision camera configuration by ID.

    Path Parameters:
    - project_id: UUID of the project
    - config_id: UUID of the camera configuration
    """
    _ = context
    return await _vision_camera_configs.get_camera_config(
        session=session,
        project_id=project_id,
        config_id=config_id,
    )


@operation_router.patch(
    "/projects/{project_id}/camera-configs/{config_id}",
    response_model=CameraConfigResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def update_camera_config(
    project_id: uuid.UUID,
    config_id: uuid.UUID,
    request: UpdateCameraConfigRequest,
    context: UserContext = Depends(
        require_project_permission("project.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> CameraConfigResponse:
    """
    Update a vision camera configuration.

    Path Parameters:
    - project_id: UUID of the project
    - config_id: UUID of the camera configuration
    """
    _ = context
    return await _vision_camera_configs.update_camera_config(
        session=session,
        project_id=project_id,
        config_id=config_id,
        request=request,
    )


@operation_router.delete(
    "/projects/{project_id}/camera-configs/{config_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def delete_camera_config(
    project_id: uuid.UUID,
    config_id: uuid.UUID,
    context: UserContext = Depends(
        require_project_permission("project.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> None:
    """
    Delete a vision camera configuration.

    Path Parameters:
    - project_id: UUID of the project
    - config_id: UUID of the camera configuration
    """
    _ = context
    return await _vision_camera_configs.delete_camera_config(
        session=session,
        project_id=project_id,
        config_id=config_id,
    )


# ==============================================================================
# CAMERA-ENTITY MAPPING ENDPOINTS
# ==============================================================================


@operation_router.post(
    "/projects/{project_id}/camera-configs/{config_id}/entities",
    status_code=status.HTTP_201_CREATED,
    response_model=CameraEntityResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def assign_entity_to_camera(
    project_id: uuid.UUID,
    config_id: uuid.UUID,
    request: AssignEntityRequest,
    context: UserContext = Depends(
        require_project_permission("project.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> CameraEntityResponse:
    """
    Assign an entity to a camera configuration with an optional ROI hint.

    Path Parameters:
    - project_id: UUID of the project
    - config_id: UUID of the camera configuration
    """
    _ = context
    return await _vision_camera_configs.assign_entity_to_camera(
        session=session,
        project_id=project_id,
        config_id=config_id,
        request=request,
    )


@operation_router.get(
    "/projects/{project_id}/camera-configs/{config_id}/entities",
    response_model=ListCameraEntitiesResponse,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def list_camera_entities(
    project_id: uuid.UUID,
    config_id: uuid.UUID,
    context: UserContext = Depends(
        require_project_permission("project.read", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> ListCameraEntitiesResponse:
    """
    List all entities assigned to a camera configuration.

    Path Parameters:
    - project_id: UUID of the project
    - config_id: UUID of the camera configuration
    """
    _ = context
    return await _vision_camera_configs.list_camera_entities(
        session=session,
        project_id=project_id,
        config_id=config_id,
    )


@operation_router.get(
    "/projects/{project_id}/entities/{entity_id}/cameras",
    response_model=ListCameraEntitiesResponse,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def list_cameras_for_entity(
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
    context: UserContext = Depends(
        require_project_permission("project.read", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> ListCameraEntitiesResponse:
    """
    List all cameras that can see a given entity.

    Path Parameters:
    - project_id: UUID of the project
    - entity_id: UUID of the entity
    """
    _ = context
    return await _vision_camera_configs.list_cameras_for_entity(
        session=session,
        project_id=project_id,
        entity_id=entity_id,
    )


@operation_router.patch(
    "/projects/{project_id}/camera-configs/{config_id}/entities/{entity_id}",
    response_model=CameraEntityResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def update_camera_entity(
    project_id: uuid.UUID,
    config_id: uuid.UUID,
    entity_id: uuid.UUID,
    request: UpdateCameraEntityRequest,
    context: UserContext = Depends(
        require_project_permission("project.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> CameraEntityResponse:
    """
    Update the ROI hint for a camera-entity mapping.

    Path Parameters:
    - project_id: UUID of the project
    - config_id: UUID of the camera configuration
    - entity_id: UUID of the entity
    """
    _ = context
    return await _vision_camera_configs.update_camera_entity(
        session=session,
        project_id=project_id,
        config_id=config_id,
        entity_id=entity_id,
        request=request,
    )


@operation_router.delete(
    "/projects/{project_id}/camera-configs/{config_id}/entities/{entity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def unassign_entity_from_camera(
    project_id: uuid.UUID,
    config_id: uuid.UUID,
    entity_id: uuid.UUID,
    context: UserContext = Depends(
        require_project_permission("project.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> None:
    """
    Remove an entity from a camera configuration.

    Path Parameters:
    - project_id: UUID of the project
    - config_id: UUID of the camera configuration
    - entity_id: UUID of the entity
    """
    _ = context
    return await _vision_camera_configs.unassign_entity_from_camera(
        session=session,
        project_id=project_id,
        config_id=config_id,
        entity_id=entity_id,
    )


# ==============================================================================
# MONITORING CONFIGURATION ENDPOINTS
# ==============================================================================


@operation_router.post(
    "/projects/{project_id}/monitoring/configs",
    status_code=status.HTTP_201_CREATED,
    response_model=MonitoringConfigResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def create_monitoring_config(
    project_id: uuid.UUID,
    signal_source_id: uuid.UUID = Form(...),
    name: str = Form(...),
    description: str | None = Form(None),
    monitoring_context: str | None = Form(None, alias="context"),
    prompt: str | None = Form(
        None,
        deprecated=True,
        description="Deprecated. Use 'context' instead.",
    ),
    pass_criteria: str | None = Form(None),
    fail_criteria: str | None = Form(None),
    structured_output: str | None = Form(None),
    model: str | None = Form(None),
    enabled: bool = Form(True),
    tags: str | None = Form(None, description="JSON array of tag strings"),
    monitoring_time_window: str | None = Form(None),
    reference_images: list[UploadFile] = File(default=[]),
    reference_image_descriptions: list[str] = Form(default=[]),
    reference_image_flags: list[str] = Form(default=[]),
    user_context: UserContext = Depends(
        require_project_permission("project.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> MonitoringConfigResponse:
    """
    Create a new monitoring configuration with optional reference image uploads.
    """
    import json

    from api.schemas.operations.monitoring import (
        AIAnalysisRules,
        ModelConfig,
        StructuredOutputField,
    )

    _ = user_context  # Used by require_project_permission

    # Resolve context field: prefer 'context' form field, fall back to 'prompt'
    resolved_context = monitoring_context or prompt
    if not resolved_context:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either 'context' or 'prompt' must be provided",
        )

    # Parse pass_criteria if provided
    parsed_pass_criteria: list[str] = []
    if pass_criteria:
        try:
            parsed_pass_criteria = json.loads(pass_criteria)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid pass_criteria format: {e!s}",
            ) from e
        if not isinstance(parsed_pass_criteria, list) or not all(
            isinstance(item, str) for item in parsed_pass_criteria
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="pass_criteria must be a JSON array of strings",
            )

    # Parse fail_criteria if provided
    parsed_fail_criteria: list[str] = []
    if fail_criteria:
        try:
            parsed_fail_criteria = json.loads(fail_criteria)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid fail_criteria format: {e!s}",
            ) from e
        if not isinstance(parsed_fail_criteria, list) or not all(
            isinstance(item, str) for item in parsed_fail_criteria
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="fail_criteria must be a JSON array of strings",
            )

    # Validate that number of images matches number of descriptions and flags
    if len(reference_images) != len(reference_image_descriptions):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Number of images ({len(reference_images)}) must match number of descriptions ({len(reference_image_descriptions)})",
        )
    if reference_image_flags and len(reference_images) != len(reference_image_flags):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Number of images ({len(reference_images)}) must match number of flags ({len(reference_image_flags)})",
        )
    # Validate flag values
    for flag in reference_image_flags:
        if flag not in ("pass", "fail"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid reference_image_flag: '{flag}'. Must be 'pass' or 'fail'",
            )

    # Parse structured_output if provided
    parsed_structured_output = None
    if structured_output:
        try:
            structured_output_data = json.loads(structured_output)
            parsed_structured_output = [
                StructuredOutputField(**field) for field in structured_output_data
            ]
        except (json.JSONDecodeError, ValueError) as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid structured_output format: {str(e)}",
            )

    # Parse model if provided
    parsed_model = None
    if model:
        try:
            model_data = json.loads(model)
            parsed_model = ModelConfig(**model_data)
        except (json.JSONDecodeError, ValueError) as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid model format: {str(e)}",
            )

    # Parse monitoring_time_window if provided
    parsed_time_window = None
    if monitoring_time_window:
        try:
            time_window_data = json.loads(monitoring_time_window)
            parsed_time_window = MonitoringTimeWindow(**time_window_data)
        except (json.JSONDecodeError, ValueError) as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid monitoring_time_window format: {str(e)}",
            )

    # Parse tags if provided
    parsed_tags: list[str] = []
    if tags:
        try:
            parsed_tags = json.loads(tags)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid tags format: {e!s}",
            ) from e
        if not isinstance(parsed_tags, list) or not all(
            isinstance(t, str) for t in parsed_tags
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="tags must be a JSON array of strings",
            )

    # Build the request object from form fields
    rules = AIAnalysisRules(
        context=resolved_context,
        prompt=prompt,
        pass_criteria=parsed_pass_criteria,
        fail_criteria=parsed_fail_criteria,
        reference_images=[],  # Will be populated after upload
        structured_output=parsed_structured_output,
        monitoring_time_window=parsed_time_window,
    )

    request = CreateMonitoringConfigRequest(
        signal_source_id=signal_source_id,
        name=name,
        description=description,
        rules=rules,
        model=parsed_model,
        enabled=enabled,
        tags=parsed_tags,
    )

    return await _monitoring.create_monitoring_config(
        project_id=project_id,
        request=request,
        reference_images=reference_images,
        reference_image_descriptions=reference_image_descriptions,
        reference_image_flags=reference_image_flags,
        session=session,
    )


@operation_router.get(
    "/projects/{project_id}/monitoring/configs",
    response_model=ListMonitoringConfigsResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def list_monitoring_configs(
    project_id: uuid.UUID,
    enabled: bool | None = Query(None, description="Filter by enabled status"),
    signal_source_id: uuid.UUID | None = Query(
        None, description="Filter by signal source"
    ),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    context: UserContext = Depends(
        require_project_permission("project.read", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> ListMonitoringConfigsResponse:
    """
    List monitoring configurations for a project.

    Path Parameters:
    - project_id: UUID of the project

    Query Parameters:
    - enabled (optional): Filter by enabled status
    - signal_source_id (optional): Filter by signal source UUID
    - page (optional, default: 1): Page number
    - page_size (optional, default: 10): Items per page

    Returns:
    - ListMonitoringConfigsResponse with paginated results
    """
    _ = context  # Used by require_project_permission
    return await _monitoring.list_monitoring_configs(
        session=session,
        project_id=project_id,
        enabled=enabled,
        signal_source_id=signal_source_id,
        page=page,
        page_size=page_size,
    )


@operation_router.get(
    "/projects/{project_id}/monitoring/configs/{config_id}",
    response_model=MonitoringConfigResponse,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_monitoring_config(
    project_id: uuid.UUID,
    config_id: uuid.UUID,
    context: UserContext = Depends(
        require_project_permission("project.read", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> MonitoringConfigResponse:
    """
    Get a monitoring configuration by ID.

    Path Parameters:
    - project_id: UUID of the project
    - config_id: UUID of the monitoring configuration

    Returns:
    - MonitoringConfigResponse with config details
    """
    _ = context  # Used by require_project_permission
    return await _monitoring.get_monitoring_config(
        config_id=config_id,
        session=session,
        project_id=project_id,
    )


@operation_router.patch(
    "/projects/{project_id}/monitoring/configs/{config_id}",
    response_model=MonitoringConfigResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def update_monitoring_config(
    project_id: uuid.UUID,
    config_id: uuid.UUID,
    name: str | None = Form(None),
    description: str | None = Form(None),
    prompt: str | None = Form(
        None,
        deprecated=True,
        description="Deprecated. Use 'context' instead.",
    ),
    monitoring_context: str | None = Form(None, alias="context"),
    pass_criteria: str | None = Form(None),
    fail_criteria: str | None = Form(None),
    structured_output: str | None = Form(None),
    model: str | None = Form(None),
    enabled: bool | None = Form(None),
    tags: str | None = Form(
        None, description="JSON array of tag strings. Pass '[]' to clear."
    ),
    monitoring_time_window: str | None = Form(None),
    # Reference image operations (send only what changes)
    add_images: list[UploadFile] = File(default=[]),
    add_descriptions: list[str] = Form(default=[]),
    add_image_flags: list[str] = Form(default=[]),
    remove_image_ids: list[str] = Form(default=[]),
    update_descriptions: list[str] = Form(
        default=[],
        deprecated=True,
        description="Deprecated. Use 'update_images' instead.",
    ),
    update_images: list[str] = Form(default=[]),
    user_context: UserContext = Depends(
        require_project_permission("project.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> MonitoringConfigResponse:
    """
    Update a monitoring configuration with simple operation-based image management.

    Cannot change project_id or signal_source_id.

    Path Parameters:
    - project_id: UUID of the project
    - config_id: UUID of the monitoring configuration

    Request Body (multipart/form-data, all optional):
    - name: New name (must be unique per project)
    - description: Updated description
    - prompt: Updated AI analysis prompt
    - model: JSON string with LLM model configuration (e.g., '{"provider": "google", "model": "gemini-3-flash-preview"}')
    - enabled: Updated enabled status
    - monitoring_time_window: JSON string for allowed execution time window

    Reference Image Operations (send only what you want to change):
    - add_images: New image files to add
    - add_descriptions: Descriptions for new images (must match add_images count)
    - remove_image_ids: List of image UUIDs to remove
    - update_descriptions: JSON array of {"id": "uuid", "description": "new desc"} to update descriptions only
    - update_images: JSON array of {"id": "uuid", "description"?: "new desc", "flag"?: "pass|fail"} to update existing image metadata

    Returns:
    - MonitoringConfigResponse with updated config details and presigned image URLs

    Examples:
    1. Add new images:
       add_images=[file1, file2]
       add_descriptions=["desc1", "desc2"]

    2. Remove images:
       remove_image_ids=["uuid1", "uuid2"]

    3. Update description only:
       update_descriptions=[{"id": "uuid1", "description": "new desc"}]

    4. Combination:
       add_images=[file1]
       add_descriptions=["new image"]
       remove_image_ids=["uuid2"]
       update_images=[{"id": "uuid3", "description": "updated", "flag": "fail"}]

    5. Remove all:
       remove_image_ids=[list all current image IDs]
    """
    _ = user_context  # Used by require_project_permission

    # Unit tests may call this function directly (outside FastAPI form parsing).
    # Normalize unparsed Form defaults to empty lists.
    if not isinstance(update_descriptions, list):
        update_descriptions = []
    if not isinstance(update_images, list):
        update_images = []

    # Validate add operations
    if add_images and len(add_images) != len(add_descriptions):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Number of add_images ({len(add_images)}) must match "
            f"number of add_descriptions ({len(add_descriptions)})",
        )

    # Validate add_image_flags if provided
    if add_image_flags and len(add_image_flags) != len(add_images):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Number of add_image_flags ({len(add_image_flags)}) must match "
            f"number of add_images ({len(add_images)})",
        )
    for flag in add_image_flags:
        if flag not in ("pass", "fail"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid add_image_flag: '{flag}'. Must be 'pass' or 'fail'",
            )

    import json

    # Parse pass_criteria if provided
    parsed_pass_criteria: list[str] | None = None
    if pass_criteria:
        try:
            parsed_pass_criteria = json.loads(pass_criteria)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid pass_criteria format: {e!s}",
            ) from e
        if not isinstance(parsed_pass_criteria, list) or not all(
            isinstance(item, str) for item in parsed_pass_criteria
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="pass_criteria must be a JSON array of strings",
            )

    # Parse fail_criteria if provided
    parsed_fail_criteria: list[str] | None = None
    if fail_criteria:
        try:
            parsed_fail_criteria = json.loads(fail_criteria)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid fail_criteria format: {e!s}",
            ) from e
        if not isinstance(parsed_fail_criteria, list) or not all(
            isinstance(item, str) for item in parsed_fail_criteria
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="fail_criteria must be a JSON array of strings",
            )

    # Parse update_descriptions / update_images JSON
    import json

    update_image_metadata_map: dict[str, dict[str, str]] = {}
    if update_descriptions:
        malformed_entries: list[dict] = []
        try:
            for idx, update_json in enumerate(update_descriptions):
                update_obj = json.loads(update_json)
                # Validate required fields
                if (
                    not isinstance(update_obj, dict)
                    or "id" not in update_obj
                    or "description" not in update_obj
                ):
                    logger.warning(
                        f"update_descriptions[{idx}] missing required fields: "
                        f"raw='{update_json}', parsed={update_obj}"
                    )
                    malformed_entries.append(
                        {
                            "index": idx,
                            "raw": update_json,
                            "parsed": update_obj,
                            "missing_fields": [
                                field
                                for field in ["id", "description"]
                                if field not in update_obj
                            ],
                        }
                    )
                else:
                    update_image_metadata_map[update_obj["id"]] = {
                        "description": update_obj["description"]
                    }
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid JSON in update_descriptions: {e}",
            )

        # Raise error if any entries were malformed
        if malformed_entries:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "Invalid update_descriptions entries",
                    "message": "One or more entries are missing required fields ('id' and 'description')",
                    "malformed_entries": malformed_entries,
                },
            )

    if update_images:
        malformed_entries: list[dict] = []
        try:
            for idx, update_json in enumerate(update_images):
                update_obj = json.loads(update_json)
                if not isinstance(update_obj, dict):
                    malformed_entries.append(
                        {
                            "index": idx,
                            "raw": update_json,
                            "parsed": update_obj,
                            "message": "Entry must be a JSON object",
                        }
                    )
                    continue

                image_id = update_obj.get("id")
                has_description = "description" in update_obj
                has_flag = "flag" in update_obj

                if not image_id:
                    malformed_entries.append(
                        {
                            "index": idx,
                            "raw": update_json,
                            "parsed": update_obj,
                            "message": "Missing required field 'id'",
                        }
                    )
                    continue

                if not has_description and not has_flag:
                    malformed_entries.append(
                        {
                            "index": idx,
                            "raw": update_json,
                            "parsed": update_obj,
                            "message": "At least one of 'description' or 'flag' must be provided",
                        }
                    )
                    continue

                if has_flag and update_obj["flag"] not in ("pass", "fail"):
                    malformed_entries.append(
                        {
                            "index": idx,
                            "raw": update_json,
                            "parsed": update_obj,
                            "message": f"Invalid flag '{update_obj['flag']}'. Must be 'pass' or 'fail'",
                        }
                    )
                    continue

                existing_update = update_image_metadata_map.setdefault(image_id, {})
                if has_description:
                    existing_update["description"] = update_obj["description"]
                if has_flag:
                    existing_update["flag"] = update_obj["flag"]
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid JSON in update_images: {e}",
            )

        if malformed_entries:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "Invalid update_images entries",
                    "message": "One or more update_images entries are malformed",
                    "malformed_entries": malformed_entries,
                },
            )

    # Parse structured_output if provided
    from api.schemas.operations.monitoring import ModelConfig, StructuredOutputField

    parsed_structured_output = None
    if structured_output:
        try:
            structured_output_data = json.loads(structured_output)
            parsed_structured_output = [
                StructuredOutputField(**field) for field in structured_output_data
            ]
        except (json.JSONDecodeError, ValueError) as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid structured_output format: {str(e)}",
            )

    # Parse model if provided
    parsed_model = None
    if model:
        try:
            model_data = json.loads(model)
            parsed_model = ModelConfig(**model_data)
        except (json.JSONDecodeError, ValueError) as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid model format: {str(e)}",
            )

    # Parse monitoring_time_window if provided
    parsed_time_window = None
    if monitoring_time_window:
        try:
            time_window_data = json.loads(monitoring_time_window)
            parsed_time_window = MonitoringTimeWindow(**time_window_data)
        except (json.JSONDecodeError, ValueError) as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid monitoring_time_window format: {str(e)}",
            )

    # Parse tags if provided
    parsed_tags: list[str] | None = None
    if tags is not None:
        try:
            parsed_tags = json.loads(tags)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid tags format: {e!s}",
            ) from e
        if not isinstance(parsed_tags, list) or not all(
            isinstance(t, str) for t in parsed_tags
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="tags must be a JSON array of strings",
            )

    # Build request object
    request = UpdateMonitoringConfigRequest(
        name=name,
        description=description,
        context=monitoring_context,
        prompt=prompt,
        pass_criteria=parsed_pass_criteria,
        fail_criteria=parsed_fail_criteria,
        structured_output=parsed_structured_output,
        model=parsed_model,
        enabled=enabled,
        monitoring_time_window=parsed_time_window,
        tags=parsed_tags,
    )

    return await _monitoring.update_monitoring_config(
        config_id=config_id,
        request=request,
        session=session,
        project_id=project_id,
        add_images=add_images,
        add_descriptions=add_descriptions,
        add_image_flags=add_image_flags,
        remove_image_ids=remove_image_ids,
        update_image_metadata=update_image_metadata_map,
    )


@operation_router.delete(
    "/projects/{project_id}/monitoring/configs/{config_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def delete_monitoring_config(
    project_id: uuid.UUID,
    config_id: uuid.UUID,
    context: UserContext = Depends(
        require_project_permission("project.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> None:
    """
    Delete a monitoring configuration.

    Path Parameters:
    - project_id: UUID of the project
    - config_id: UUID of the monitoring configuration
    """
    _ = context  # Used by require_project_permission
    return await _monitoring.delete_monitoring_config(
        config_id=config_id,
        session=session,
        project_id=project_id,
    )


@operation_router.post(
    "/projects/{project_id}/monitoring/configs/{config_id}/run",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TriggerRunResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def trigger_monitoring_run(
    project_id: uuid.UUID,
    config_id: uuid.UUID,
    request: TriggerRunRequest,
    context: UserContext = Depends(
        require_project_permission("project.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> TriggerRunResponse:
    """
    Trigger a manual monitoring run.

    Path Parameters:
    - project_id: UUID of the project
    - config_id: UUID of the monitoring configuration

    Request Body (all optional):
    - s3_bucket: S3 bucket for image source
    - s3_key: S3 key for image source

    Returns:
    - TriggerRunResponse with run details
    """
    return await _monitoring.trigger_monitoring_run(
        config_id=config_id,
        request=request,
        session=session,
        project_id=project_id,
        user_id=context.username,
    )


@operation_router.post(
    "/projects/{project_id}/monitoring/configs/{config_id}/test",
    status_code=status.HTTP_200_OK,
    response_model=TestMonitoringConfigResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def test_monitoring_config(
    project_id: uuid.UUID,
    config_id: uuid.UUID,
    test_image: UploadFile | None = File(None),
    s3_url: str | None = Form(None),
    context: UserContext = Depends(
        require_project_permission("project.read", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> TestMonitoringConfigResponse:
    """
    Test a monitoring configuration without saving to database.

    Automatically detects whether the config is for image or video monitoring and uses
    the appropriate analysis method.

    For IMAGE monitoring:
    - Users can provide: uploaded test image, S3 URL, or use latest feed capture
    - Priority: uploaded file > S3 URL > latest feed
    - Runs image analysis and returns results including confidence scores

    For VIDEO monitoring:
    - Users can provide: S3 URL or use latest feed capture
    - Uploaded test videos are NOT supported (only S3 URLs or feed videos)
    - Runs video analysis (native video or frame extraction based on model)

    This allows users to preview how the monitoring will analyze media before
    committing the configuration.

    Path Parameters:
    - project_id: UUID of the project
    - config_id: UUID of the monitoring configuration

    Form Data (optional):
    - test_image: Custom test image file (only for image configs)
    - s3_url: S3 key/path to test image or video (e.g., "security/cameras/...")

    Priority:
    - If test_image provided: uses uploaded file (image configs only)
    - Else if s3_url provided: uses S3 media (both image and video configs)
    - Else: uses latest feed capture

    Returns:
    - TestMonitoringConfigResponse with:
      - evaluation_result: The analysis result that would be saved to DB
      - error_message: Error details if result='error'
      - prompt_sent: Debug info about what was sent to LLM
      - test_image_url: S3 key of the analyzed media (image or video)
      - test_image_source: Description of media source
    """
    _ = context  # Used by require_project_permission
    return await _monitoring.test_monitoring_config(
        config_id=config_id,
        session=session,
        project_id=project_id,
        test_image=test_image,
        s3_url=s3_url,
    )


# ==============================================================================
# MONITORING RUN ENDPOINTS
# ==============================================================================


@operation_router.get(
    "/projects/{project_id}/monitoring/configs/{monitoring_config_id}/runs",
    response_model=ListMonitoringRunsResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def list_monitoring_runs(
    project_id: uuid.UUID,
    monitoring_config_id: uuid.UUID,
    start_date: datetime | None = Query(
        None, description="Filter runs after this date (ISO 8601)"
    ),
    end_date: datetime | None = Query(
        None, description="Filter runs before this date (ISO 8601)"
    ),
    result: str | None = Query(
        None, description="Filter by result (pass, fail, error)"
    ),
    context: UserContext = Depends(
        require_project_permission("project.read", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> ListMonitoringRunsResponse:
    """
    List monitoring runs for a configuration.

    Path Parameters:
    - project_id: UUID of the project
    - monitoring_config_id: UUID of the monitoring config

    Query Parameters:
    - start_date (optional): Filter runs after this date
    - end_date (optional): Filter runs before this date
    - result (optional): Filter by result ('pass', 'fail', 'error')

    Returns:
    - ListMonitoringRunsResponse with all runs
    """
    _ = context  # Used by require_project_permission
    return await _monitoring.list_monitoring_runs(
        session=session,
        monitoring_config_id=monitoring_config_id,
        project_id=project_id,
        start_date=start_date,
        end_date=end_date,
        result=result,
    )


@operation_router.get(
    "/projects/{project_id}/monitoring/runs/{run_id}",
    response_model=MonitoringRunResponse,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_monitoring_run(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    context: UserContext = Depends(
        require_project_permission("project.read", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> MonitoringRunResponse:
    """
    Get a monitoring run by ID.

    Path Parameters:
    - project_id: UUID of the project
    - run_id: UUID of the monitoring run

    Returns:
    - MonitoringRunResponse with run details
    """
    _ = context  # Used by require_project_permission
    return await _monitoring.get_monitoring_run(
        run_id=run_id,
        session=session,
        project_id=project_id,
    )


@operation_router.delete(
    "/projects/{project_id}/monitoring/runs/{run_id}",
    response_model=dict,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def delete_monitoring_run(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    context: UserContext = Depends(
        require_project_permission("project.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> dict:
    """
    Delete a monitoring run by ID.

    Path Parameters:
    - project_id: UUID of the project
    - run_id: UUID of the monitoring run

    Returns:
    - Success message
    """
    _ = context  # Used by require_project_permission
    return await _monitoring.delete_monitoring_run(
        run_id=run_id,
        session=session,
        project_id=project_id,
    )


@operation_router.post(
    "/projects/{project_id}/monitoring/runs/batch-delete",
    response_model=BatchDeleteMonitoringRunsResponse,
    responses={
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def batch_delete_monitoring_runs(
    project_id: uuid.UUID,
    request: BatchDeleteMonitoringRunsRequest,
    context: UserContext = Depends(
        require_project_permission("project.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> BatchDeleteMonitoringRunsResponse:
    """
    Delete multiple monitoring runs by IDs.

    Path Parameters:
    - project_id: UUID of the project

    Request Body:
    - run_ids: List of monitoring run UUIDs to delete

    Returns:
    - BatchDeleteMonitoringRunsResponse with deletion statistics
    """
    _ = context  # Used by require_project_permission
    return await _monitoring.batch_delete_monitoring_runs(
        request=request,
        session=session,
        project_id=project_id,
    )


@operation_router.post(
    "/projects/{project_id}/monitoring/runs/{run_id}/rerun",
    response_model=RerunMonitoringRunResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def rerun_monitoring_run(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    context: UserContext = Depends(
        require_project_permission("project.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> RerunMonitoringRunResponse:
    """
    Rerun a monitoring run analysis.

    Triggers a reanalysis of the monitoring run using the original media.
    The analysis runs in the background, and this endpoint returns immediately
    with a "processing" status.

    The evaluation_result will show "processing" status and be updated with the
    new analysis results when complete. The completed_at timestamp is preserved
    from the original run.

    Automatically detects whether the original run was for image or video monitoring
    and uses the appropriate analysis method.

    Path Parameters:
    - project_id: UUID of the project
    - run_id: UUID of the monitoring run to rerun

    Returns:
    - RerunMonitoringRunResponse with processing status
    """
    _ = context  # Used by require_project_permission
    return await _monitoring.rerun_monitoring_run(
        run_id=run_id,
        session=session,
        project_id=project_id,
    )


@operation_router.get(
    "/projects/{project_id}/monitoring/summary",
    response_model=None,
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_monitoring_summary(
    project_id: uuid.UUID,
    context: UserContext = Depends(
        require_project_permission("project.read", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict[str, Any]:
    """Get monitoring health summary for a project, grouped by tags.

    Returns per-tag health status (critical/warning/healthy) based on fail rate
    within the specified time range. Used by the dashboard to render project
    location cards with tag-level health indicators.

    Query Parameters:
    - start_date: Optional start of time range (inclusive)
    - end_date: Optional end of time range (inclusive)
    """
    _ = context  # Used by require_project_permission
    return await _monitoring.get_monitoring_summary(
        session=session,
        project_id=project_id,
        start_date=start_date,
        end_date=end_date,
    )


# ==============================================================================
# ROUTINE ENDPOINTS
# ==============================================================================


@operation_router.post(
    "/projects/{project_id}/routines",
    status_code=status.HTTP_201_CREATED,
    response_model=RoutineDetailResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        409: {
            "model": ErrorResponse,
            "description": "Routine with this name already exists",
        },
        500: {"model": ErrorResponse},
    },
)
async def create_routine(
    project_id: uuid.UUID,
    request: CreateRoutineRequest,
    context: UserContext = Depends(
        require_project_permission("project.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> RoutineDetailResponse:
    """
    Create a new routine with optional items and schedule.

    Path Parameters:
    - project_id: UUID of the project

    Request Body:
    - name (required): Name of the routine
    - description (optional): Description
    - category (required): Category (opening, closing, food_safety, custom)
    - is_active (optional, default: true): Whether routine is active
    - items (optional): List of routine items to create
    - schedule (optional): Schedule configuration

    Returns:
    - RoutineDetailResponse with the created routine and items
    """
    return await _routines.create_routine(project_id, request, context, session)


@operation_router.get(
    "/projects/{project_id}/routines",
    response_model=ListRoutinesResponse,
    responses={
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def list_routines(
    project_id: uuid.UUID,
    is_active: bool | None = Query(None, description="Filter by active status"),
    context: UserContext = Depends(
        require_project_permission("project.read", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> ListRoutinesResponse:
    """
    List routines for a project.

    Path Parameters:
    - project_id: UUID of the project

    Query Parameters:
    - is_active (optional): Filter by active status

    Returns:
    - ListRoutinesResponse with routines and total count
    """
    return await _routines.list_routines(project_id, context, session, is_active)


@operation_router.get(
    "/routines/{routine_id}",
    response_model=RoutineDetailResponse,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_routine(
    routine_id: uuid.UUID,
    context: Annotated[
        UserContext,
        Depends(require_routine_permission("routine.read", authenticate_user)),
    ],
    session: Annotated[AsyncSession, Depends(db.get_db_async)],
) -> RoutineDetailResponse:
    """
    Get a routine by ID with its items.

    Path Parameters:
    - routine_id: UUID of the routine

    Returns:
    - RoutineDetailResponse with routine details and items
    """
    return await _routines.get_routine(routine_id, context, session)


@operation_router.patch(
    "/routines/{routine_id}",
    response_model=RoutineResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def update_routine(
    routine_id: uuid.UUID,
    request: UpdateRoutineRequest,
    context: Annotated[
        UserContext,
        Depends(require_routine_permission("routine.write", authenticate_user)),
    ],
    session: Annotated[AsyncSession, Depends(db.get_db_async)],
) -> RoutineResponse:
    """
    Update a routine.

    Path Parameters:
    - routine_id: UUID of the routine

    Request Body (all optional):
    - name: New name
    - description: Updated description
    - category: Updated category
    - is_active: Updated active status

    Returns:
    - RoutineResponse with updated routine
    """
    return await _routines.update_routine(routine_id, request, context, session)


@operation_router.delete(
    "/routines/{routine_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def delete_routine(
    routine_id: uuid.UUID,
    context: Annotated[
        UserContext,
        Depends(require_routine_permission("routine.write", authenticate_user)),
    ],
    session: Annotated[AsyncSession, Depends(db.get_db_async)],
) -> None:
    """
    Delete a routine.

    Path Parameters:
    - routine_id: UUID of the routine
    """
    await _routines.delete_routine(routine_id, context, session)


# ==============================================================================
# ROUTINE ITEM ENDPOINTS
# ==============================================================================


@operation_router.post(
    "/routines/{routine_id}/items",
    status_code=status.HTTP_201_CREATED,
    response_model=RoutineItemResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def add_routine_item(
    routine_id: uuid.UUID,
    request: CreateRoutineItemRequest,
    context: Annotated[
        UserContext,
        Depends(require_routine_permission("routine.write", authenticate_user)),
    ],
    session: Annotated[AsyncSession, Depends(db.get_db_async)],
) -> RoutineItemResponse:
    """
    Add an item to a routine.

    Path Parameters:
    - routine_id: UUID of the routine

    Request Body:
    - name (required): Name of the item
    - description (optional): Description
    - input_type (required): Input type (photo, checkbox, number, text)
    - is_required (optional, default: true): Whether item is required
    - sort_order (optional): Sort order
    - ai_rules (optional): AI verification rules

    Returns:
    - RoutineItemResponse with created item
    """
    return await _routines.add_item(routine_id, request, context, session)


@operation_router.patch(
    "/routine-items/{item_id}",
    response_model=RoutineItemResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def update_routine_item(
    item_id: uuid.UUID,
    request: UpdateRoutineItemRequest,
    context: UserContext = Depends(authenticate_user),
    session: AsyncSession = Depends(db.get_db_async),
) -> RoutineItemResponse:
    """
    Update a routine item.

    Path Parameters:
    - item_id: UUID of the routine item

    Request Body (all optional):
    - name: New name
    - description: Updated description
    - input_type: Updated input type
    - is_required: Updated required status
    - sort_order: Updated sort order
    - ai_rules: Updated AI rules

    Returns:
    - RoutineItemResponse with updated item
    """
    return await _routines.update_item(item_id, request, context, session)


@operation_router.delete(
    "/routine-items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def delete_routine_item(
    item_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: AsyncSession = Depends(db.get_db_async),
) -> None:
    """
    Delete a routine item.

    Path Parameters:
    - item_id: UUID of the routine item
    """
    await _routines.delete_item(item_id, context, session)


@operation_router.post(
    "/routine-items/{item_id}/reference-image",
    response_model=dict[str, str],
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def upload_routine_item_reference_image(
    item_id: uuid.UUID,
    file: UploadFile = File(...),
    description: str = Form(default=""),
    context: UserContext = Depends(authenticate_user),
    session: AsyncSession = Depends(db.get_db_async),
) -> dict[str, str]:
    """
    Upload a reference image for a routine item.

    This endpoint appends a new reference image to the routine item's existing
    list of reference images. To upload multiple images, call this endpoint
    multiple times.

    Path Parameters:
    - item_id: UUID of the routine item

    Request Body (multipart/form-data):
    - file (required): Image file
    - description (optional): Description of the reference image

    Returns:
    - Dict with 'image_url' and 'description' fields for the newly uploaded image
    """
    return await _routines.upload_reference_image(
        item_id, file, description, context, session
    )


@operation_router.patch(
    "/routine-items/{item_id}/reference-images",
    response_model=list[dict[str, str]],
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def update_routine_item_reference_images(
    item_id: uuid.UUID,
    request: UpdateReferenceImagesRequest,
    context: UserContext = Depends(authenticate_user),
    session: AsyncSession = Depends(db.get_db_async),
) -> list[dict[str, str]]:
    """
    Update the complete list of reference images for a routine item.

    This endpoint replaces the entire list of reference images. It intelligently
    handles S3 storage:
    - Keeps images that appear in both old and new lists (matched by image_url)
    - Deletes images from S3 that are removed from the list
    - New images should already be uploaded (have image_url populated)

    **Workflow:**
    1. User uploads new images individually using POST /routine-items/{item_id}/reference-image
    2. User calls this PATCH endpoint with the complete desired list (existing + new URLs)
    3. Backend compares lists and deletes removed images from S3

    Path Parameters:
    - item_id: UUID of the routine item

    Request Body (application/json):
    - reference_images (required): Complete list of reference images
      Each item should have:
      - image_url (required): S3 URL of the image
      - description (optional): Description of the image

    Returns:
    - List of dicts with 'image_url' and 'description' fields

    Example request body:
    ```json
    {
      "reference_images": [
        {
          "image_url": "https://s3.../routines/.../image1.jpg",
          "description": "Front view"
        },
        {
          "image_url": "https://s3.../routines/.../image2.jpg",
          "description": "Side view"
        }
      ]
    }
    ```
    """
    return await _routines.update_reference_images(item_id, request, context, session)


# ==============================================================================
# SCHEDULE ENDPOINTS
# ==============================================================================


@operation_router.post(
    "/routines/{routine_id}/schedules",
    status_code=status.HTTP_201_CREATED,
    response_model=ScheduleResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def create_schedule(
    routine_id: uuid.UUID,
    request: CreateScheduleRequest,
    context: UserContext = Depends(authenticate_user),
    session: AsyncSession = Depends(db.get_db_async),
) -> ScheduleResponse:
    """
    Create a schedule for a routine.

    Note: Each routine has one schedule, created automatically via the create routine
    endpoint. Use this endpoint only when a schedule needs to be recreated after deletion.
    In most cases, use create routine instead.

    Path Parameters:
    - routine_id: UUID of the routine

    Request Body:
    - frequency (required): Frequency (daily, weekly, monthly)
    - config (required): Schedule configuration
    - is_active (optional, default: true): Whether schedule is active

    Returns:
    - ScheduleResponse with created schedule
    """
    return await _routines.create_schedule(routine_id, request, context, session)


@operation_router.get(
    "/routines/{routine_id}/schedules",
    response_model=ListSchedulesResponse,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def list_schedules(
    routine_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: AsyncSession = Depends(db.get_db_async),
) -> ListSchedulesResponse:
    """
    List schedules for a routine.

    Path Parameters:
    - routine_id: UUID of the routine

    Returns:
    - ListSchedulesResponse with schedules and total count
    """
    return await _routines.list_schedules(routine_id, context, session)


@operation_router.patch(
    "/schedules/{schedule_id}",
    response_model=ScheduleResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def update_schedule(
    schedule_id: uuid.UUID,
    request: UpdateScheduleRequest,
    context: UserContext = Depends(authenticate_user),
    session: AsyncSession = Depends(db.get_db_async),
) -> ScheduleResponse:
    """
    Update a schedule.

    Path Parameters:
    - schedule_id: UUID of the schedule

    Request Body (all optional):
    - frequency: Updated frequency
    - config: Updated configuration
    - is_active: Updated active status

    Returns:
    - ScheduleResponse with updated schedule
    """
    return await _routines.update_schedule(schedule_id, request, context, session)


@operation_router.delete(
    "/schedules/{schedule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def delete_schedule(
    schedule_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: AsyncSession = Depends(db.get_db_async),
) -> None:
    """
    Delete a schedule.

    Note: Each routine has one schedule. Deleting a schedule does not delete its
    associated routine or existing executions. In most cases, use delete routine
    instead to cascade-delete the routine, schedule, and all executions together.

    Path Parameters:
    - schedule_id: UUID of the schedule
    """
    await _routines.delete_schedule(schedule_id, context, session)


# ==============================================================================
# EXECUTION ENDPOINTS
# ==============================================================================


async def _get_project_timezone(project_id: uuid.UUID, session: AsyncSession) -> str:
    """
    Get the timezone string for a project.

    Args:
        project_id: UUID of the project
        session: Async database session

    Returns:
        IANA timezone string (e.g., 'America/Los_Angeles')

    Raises:
        HTTPException: If project not found
    """
    project_repo = ProjectRepository(session)
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
            headers={"Content-Type": "application/json"},
        )

    # Validate timezone and return with fallback
    tz_str = project.timezone or "America/Los_Angeles"
    try:
        ZoneInfo(tz_str)
    except ZoneInfoNotFoundError:
        logger.warning(
            f"Invalid timezone '{project.timezone}' for project {project_id}, "
            "falling back to America/Los_Angeles"
        )
        tz_str = "America/Los_Angeles"
    return tz_str


async def _get_project_today(project_id: uuid.UUID, session: AsyncSession) -> date:
    """
    Get today's date in the project's timezone.

    Args:
        project_id: UUID of the project
        session: Async database session

    Returns:
        Today's date in the project's timezone

    Raises:
        HTTPException: If project not found
    """
    tz_str = await _get_project_timezone(project_id, session)
    project_tz = ZoneInfo(tz_str)
    return datetime.now(project_tz).date()


@operation_router.get(
    "/projects/{project_id}/executions",
    response_model=ListExecutionsResponse,
    responses={
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def list_executions(
    project_id: uuid.UUID,
    context: Annotated[
        UserContext,
        Depends(require_project_permission("execution.read.today", authenticate_user)),
    ],
    session: Annotated[AsyncSession, Depends(db.get_db_async)],
    sync_session: Annotated[Session, Depends(db.get_db)],
    status_filter: Annotated[
        ExecutionStatus | None,
        Query(alias="status", description="Filter by execution status"),
    ] = None,
    date_filter: Annotated[
        datetime | None,
        Query(alias="date", description="Filter by scheduled date (single day)"),
    ] = None,
    start_date: Annotated[
        datetime | None,
        Query(description="Filter by start date (inclusive, for date range)"),
    ] = None,
    end_date: Annotated[
        datetime | None,
        Query(description="Filter by end date (inclusive, for date range)"),
    ] = None,
    routine_id: Annotated[
        uuid.UUID | None,
        Query(description="Filter by specific routine"),
    ] = None,
    include: Annotated[
        str | None,
        Query(
            description="Include additional data: 'details' for full submission details"
        ),
    ] = None,
) -> ListExecutionsResponse:
    """
    List executions for routines in a project.

    Path Parameters:
    - project_id: UUID of the project

    Query Parameters:
    - status (optional): Filter by execution status
    - date (optional): Filter by scheduled date (single day, takes precedence over date range)
    - start_date (optional): Filter by start date (inclusive, for date range)
    - end_date (optional): Filter by end date (inclusive, for date range)
    - routine_id (optional): Filter by specific routine
    - include (optional): Include additional data ('details' for full submission details)

    Returns:
    - ListExecutionsResponse with executions and total count

    Note: Users without execution.read.history permission can only view today's executions.
    """
    # Convert datetime to date if provided
    # When date_filter is provided, it takes precedence and range filters are cleared
    if date_filter:
        date_only = date_filter.date()
        start_date_only = None
        end_date_only = None
    else:
        date_only = None
        start_date_only = start_date.date() if start_date else None
        end_date_only = end_date.date() if end_date else None

    # Get project timezone for correct date filtering
    project_timezone = await _get_project_timezone(project_id, session)

    # Check if user has history permission
    # Handle non-UUID usernames (e.g., "guest") by denying history access
    try:
        user_id = uuid.UUID(context.username)
        # Run sync permission check in thread pool to avoid blocking async event loop
        has_history_access = await run_in_threadpool(
            check_permission,
            user_id=user_id,
            resource_id=f"projects/{project_id}",
            permission_name="execution.read.history",
            session=sync_session,
        )
    except (ValueError, TypeError):
        has_history_access = False

    # If no history access, enforce today-only filter
    if not has_history_access:
        today = await _get_project_today(project_id, session)
        # Check single date filter
        if date_only and date_only != today:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Can only view today's executions",
                headers={"Content-Type": "application/json"},
            )
        # Check date range filter
        if start_date_only or end_date_only:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Can only view today's executions",
                headers={"Content-Type": "application/json"},
            )
        date_only = today
        start_date_only = None
        end_date_only = None

    return await _routines.list_executions(
        project_id,
        context,
        session,
        status_filter,
        date_only,
        start_date_only,
        end_date_only,
        routine_id,
        project_timezone,
        include_details=(include == "details"),
    )


@operation_router.get(
    "/executions/{execution_id}",
    response_model=ExecutionDetailResponse,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_execution(
    execution_id: uuid.UUID,
    context: Annotated[
        UserContext,
        Depends(
            require_execution_permission("execution.read.today", authenticate_user)
        ),
    ],
    session: Annotated[AsyncSession, Depends(db.get_db_async)],
    details: bool = Query(
        default=False,
        description="Include full routine and submission details",
    ),
) -> ExecutionDetailResponse:
    """
    Get an execution by ID.

    Path Parameters:
    - execution_id: UUID of the execution

    Query Parameters:
    - details: If true, includes full routine and submission details

    Returns:
    - ExecutionDetailResponse with execution details
    """
    return await _routines.get_execution(execution_id, context, session, details)


# ==============================================================================
# SUBMISSION ENDPOINTS - STAFF WORKFLOW
# ==============================================================================


@operation_router.post(
    "/executions/{execution_id}/submissions",
    status_code=status.HTTP_201_CREATED,
    response_model=SubmissionDetailResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def start_submission(
    execution_id: uuid.UUID,
    context: Annotated[
        UserContext,
        Depends(require_execution_permission("submission.create", authenticate_user)),
    ],
    session: Annotated[AsyncSession, Depends(db.get_db_async)],
) -> SubmissionDetailResponse:
    """
    Start a submission for an execution (creates draft).

    If a submission already exists for this execution, returns the existing one.

    Path Parameters:
    - execution_id: UUID of the execution

    Returns:
    - SubmissionDetailResponse with the draft submission
    """
    return await _routines.start_submission(execution_id, context, session)


@operation_router.get(
    "/submissions/{submission_id}",
    response_model=SubmissionDetailResponse,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_submission(
    submission_id: uuid.UUID,
    context: Annotated[
        UserContext,
        Depends(require_submission_permission("submission.create", authenticate_user)),
    ],
    session: Annotated[AsyncSession, Depends(db.get_db_async)],
) -> SubmissionDetailResponse:
    """
    Get a submission with its responses.

    Path Parameters:
    - submission_id: UUID of the submission

    Returns:
    - SubmissionDetailResponse with submission details and responses
    """
    return await _routines.get_submission(submission_id, context, session)


@operation_router.post(
    "/submissions/{submission_id}/responses",
    status_code=status.HTTP_201_CREATED,
    response_model=ItemResponseWithItemResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def add_response(
    submission_id: uuid.UUID,
    context: Annotated[
        UserContext,
        Depends(require_submission_permission("submission.write", authenticate_user)),
    ],
    session: Annotated[AsyncSession, Depends(db.get_db_async)],
    routine_item_id: uuid.UUID = Form(...),
    file: UploadFile | None = File(None),
    notes: str | None = Form(None),
) -> ItemResponseWithItemResponse:
    """
    Add a response to a submission item.

    Path Parameters:
    - submission_id: UUID of the submission

    Request Body (multipart/form-data):
    - routine_item_id (required): UUID of the routine item
    - file (optional): Image file for photo responses
    - notes (optional): Staff notes

    Returns:
    - ItemResponseWithItemResponse with the created/updated response
    """
    return await _routines.add_response(
        submission_id, routine_item_id, file, notes, context, session
    )


@operation_router.post(
    "/submissions/{submission_id}/submit",
    response_model=SubmissionResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def submit_for_review(
    submission_id: uuid.UUID,
    context: Annotated[
        UserContext,
        Depends(require_submission_permission("submission.write", authenticate_user)),
    ],
    session: Annotated[AsyncSession, Depends(db.get_db_async)],
) -> SubmissionResponse:
    """
    Submit a draft submission for manager review.

    Path Parameters:
    - submission_id: UUID of the submission

    Returns:
    - SubmissionResponse with updated submission status
    """
    return await _routines.submit_for_review(submission_id, context, session)


# ==============================================================================
# SUBMISSION ENDPOINTS - MANAGER WORKFLOW
# ==============================================================================


@operation_router.get(
    "/projects/{project_id}/submissions/pending-review",
    response_model=ListPendingReviewResponse,
    responses={
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def list_pending_review(
    project_id: uuid.UUID,
    context: Annotated[
        UserContext,
        Depends(require_project_permission("submission.review", authenticate_user)),
    ],
    session: Annotated[AsyncSession, Depends(db.get_db_async)],
    start_date: Annotated[
        datetime | None,
        Query(description="Filter by start date (inclusive, for date range)"),
    ] = None,
    end_date: Annotated[
        datetime | None,
        Query(description="Filter by end date (inclusive, for date range)"),
    ] = None,
) -> ListPendingReviewResponse:
    """
    List submissions pending manager review.

    Path Parameters:
    - project_id: UUID of the project

    Query Parameters:
    - start_date (optional): Filter by start date (inclusive, for date range)
    - end_date (optional): Filter by end date (inclusive, for date range)

    Returns:
    - ListPendingReviewResponse with pending submissions and total count
    """
    # Convert datetime to date if provided
    start_date_only = start_date.date() if start_date else None
    end_date_only = end_date.date() if end_date else None

    return await _routines.list_pending_review(
        project_id, context, session, start_date_only, end_date_only
    )


@operation_router.post(
    "/submissions/{submission_id}/approve",
    response_model=SubmissionResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def approve_submission(
    submission_id: uuid.UUID,
    context: Annotated[
        UserContext,
        Depends(require_submission_permission("submission.review", authenticate_user)),
    ],
    session: Annotated[AsyncSession, Depends(db.get_db_async)],
) -> SubmissionResponse:
    """
    Approve a submitted submission.

    Path Parameters:
    - submission_id: UUID of the submission

    Returns:
    - SubmissionResponse with approved status
    """
    return await _routines.approve_submission(submission_id, context, session)


@operation_router.post(
    "/submissions/{submission_id}/reject",
    response_model=SubmissionResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def reject_submission(
    submission_id: uuid.UUID,
    request: RejectSubmissionRequest,
    context: Annotated[
        UserContext,
        Depends(require_submission_permission("submission.review", authenticate_user)),
    ],
    session: Annotated[AsyncSession, Depends(db.get_db_async)],
) -> SubmissionResponse:
    """
    Reject a submitted submission with notes.

    Path Parameters:
    - submission_id: UUID of the submission

    Request Body:
    - review_notes (required): Reason for rejection

    Returns:
    - SubmissionResponse with rejected status
    """
    return await _routines.reject_submission(submission_id, request, context, session)


@operation_router.post(
    "/submissions/{submission_id}/reset",
    response_model=SubmissionResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def reset_to_draft(
    submission_id: uuid.UUID,
    context: Annotated[
        UserContext,
        Depends(require_submission_permission("submission.write", authenticate_user)),
    ],
    session: Annotated[AsyncSession, Depends(db.get_db_async)],
) -> SubmissionResponse:
    """
    Reset a submission back to draft status for resubmission.

    This endpoint allows resetting submissions from any status (submitted, approved, rejected)
    back to draft, enabling staff to modify responses and resubmit.

    When reset to draft:
    - Status changes to 'draft'
    - All review and submission metadata is cleared
    - Item responses remain unchanged and can be modified
    - Execution status remains 'completed'

    Path Parameters:
    - submission_id: UUID of the submission to reset

    Returns:
    - SubmissionResponse with draft status
    """
    return await _routines.reset_to_draft(submission_id, context, session)


# ==============================================================================
# VISION STATE CHANGE EVENT ENDPOINTS
# ==============================================================================


@operation_router.post(
    "/accounts/{account_name}/state-change-events",
    status_code=status.HTTP_201_CREATED,
    response_model=StateChangeEventResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def create_state_change_event(
    account_name: str,
    request: CreateStateChangeEventRequest,
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> StateChangeEventResponse:
    """
    Create a vision state change event.

    Records that an entity transitioned from one state to another.

    Path Parameters:
    - account_name: Account identifier
    """
    _ = context
    return await _vision_state_change_events.create_state_change_event(
        session=session,
        request=request,
        account_name=account_name,
    )


@operation_router.get(
    "/accounts/{account_name}/state-change-events",
    response_model=ListStateChangeEventsResponse,
    responses={
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def list_state_change_events(
    account_name: str,
    project_id: uuid.UUID | None = Query(default=None, description="Filter by project"),
    entity_id: uuid.UUID | None = Query(default=None, description="Filter by entity"),
    start: datetime | None = Query(
        default=None, description="Start time filter (defaults to 24 hours ago)"
    ),
    end: datetime | None = Query(default=None, description="End time filter"),
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> ListStateChangeEventsResponse:
    """
    List state change events.

    Returns events ordered by observed_at descending.
    Defaults to the past 24 hours if no start time is provided.

    Path Parameters:
    - account_name: Account identifier

    Query Parameters:
    - project_id (optional): Filter by project
    - entity_id (optional): Filter by entity
    - start (optional): Filter events observed after this time (default: 24h ago)
    - end (optional): Filter events observed before this time
    """
    _ = context
    effective_start = (
        start if start is not None else datetime.now(timezone.utc) - timedelta(hours=24)
    )
    return await _vision_state_change_events.list_state_change_events(
        session=session,
        account_name=account_name,
        project_id=project_id,
        entity_id=entity_id,
        start=effective_start,
        end=end,
    )


@operation_router.get(
    "/accounts/{account_name}/state-change-events/{event_id}",
    response_model=StateChangeEventResponse,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_state_change_event(
    account_name: str,
    event_id: uuid.UUID,
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> StateChangeEventResponse:
    """
    Get a state change event by ID.

    Path Parameters:
    - account_name: Account identifier
    - event_id: UUID of the event
    """
    _ = context
    return await _vision_state_change_events.get_state_change_event(
        session=session,
        event_id=event_id,
        account_name=account_name,
    )


@operation_router.put(
    "/accounts/{account_name}/state-change-events/{event_id}",
    response_model=StateChangeEventResponse,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def update_state_change_event(
    account_name: str,
    event_id: uuid.UUID,
    request: UpdateStateChangeEventRequest,
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> StateChangeEventResponse:
    """
    Update a state change event's metadata.

    Path Parameters:
    - account_name: Account identifier
    - event_id: UUID of the event
    """
    _ = context
    return await _vision_state_change_events.update_state_change_event(
        session=session,
        event_id=event_id,
        request=request,
        account_name=account_name,
    )


@operation_router.delete(
    "/accounts/{account_name}/state-change-events/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def delete_state_change_event(
    account_name: str,
    event_id: uuid.UUID,
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> None:
    """
    Delete a state change event.

    Path Parameters:
    - account_name: Account identifier
    - event_id: UUID of the event
    """
    _ = context
    return await _vision_state_change_events.delete_state_change_event(
        session=session,
        event_id=event_id,
        account_name=account_name,
    )


# ==============================================================================
# Vision Rules
# ==============================================================================


@operation_router.post(
    "/accounts/{account_name}/vision-rules",
    status_code=status.HTTP_201_CREATED,
    response_model=VisionRuleResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def create_vision_rule(
    account_name: str,
    request: CreateVisionRuleRequest,
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> VisionRuleResponse:
    """
    Create a vision rule.

    Path Parameters:
    - account_name: Account identifier
    """
    _ = context
    return await _vision_rules.create_vision_rule(
        session=session,
        request=request,
        account_name=account_name,
    )


@operation_router.get(
    "/accounts/{account_name}/vision-rules",
    response_model=ListVisionRulesResponse,
    responses={
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def list_vision_rules(
    account_name: str,
    project_id: uuid.UUID | None = Query(default=None, description="Filter by project"),
    is_active: bool | None = Query(default=None, description="Filter by active status"),
    limit: int = Query(default=100, ge=1, le=1000, description="Max results"),
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> ListVisionRulesResponse:
    """
    List vision rules.

    Path Parameters:
    - account_name: Account identifier

    Query Parameters:
    - project_id (optional): Filter by project
    - is_active (optional): Filter by active status
    - limit (optional): Max results (default 100, max 1000)
    """
    _ = context
    return await _vision_rules.list_vision_rules(
        session=session,
        account_name=account_name,
        project_id=project_id,
        is_active=is_active,
        limit=limit,
    )


@operation_router.get(
    "/accounts/{account_name}/vision-rules/{rule_id}",
    response_model=VisionRuleResponse,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_vision_rule(
    account_name: str,
    rule_id: uuid.UUID,
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> VisionRuleResponse:
    """
    Get a vision rule by ID.

    Path Parameters:
    - account_name: Account identifier
    - rule_id: UUID of the rule
    """
    _ = context
    return await _vision_rules.get_vision_rule(
        session=session,
        rule_id=rule_id,
        account_name=account_name,
    )


@operation_router.patch(
    "/accounts/{account_name}/vision-rules/{rule_id}",
    response_model=VisionRuleResponse,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def update_vision_rule(
    account_name: str,
    rule_id: uuid.UUID,
    request: UpdateVisionRuleRequest,
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> VisionRuleResponse:
    """
    Update a vision rule.

    Path Parameters:
    - account_name: Account identifier
    - rule_id: UUID of the rule
    """
    _ = context
    return await _vision_rules.update_vision_rule(
        session=session,
        rule_id=rule_id,
        request=request,
        account_name=account_name,
    )


@operation_router.delete(
    "/accounts/{account_name}/vision-rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def delete_vision_rule(
    account_name: str,
    rule_id: uuid.UUID,
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> None:
    """
    Delete a vision rule.

    Path Parameters:
    - account_name: Account identifier
    - rule_id: UUID of the rule
    """
    _ = context
    return await _vision_rules.delete_vision_rule(
        session=session,
        rule_id=rule_id,
        account_name=account_name,
    )


# ==============================================================================
# Vision Rule Events
# ==============================================================================


@operation_router.get(
    "/accounts/{account_name}/rule-events",
    response_model=ListVisionRuleEventsResponse,
    responses={
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def list_rule_events(
    account_name: str,
    rule_id: uuid.UUID | None = Query(default=None, description="Filter by rule"),
    entity_id: uuid.UUID | None = Query(default=None, description="Filter by entity"),
    start: datetime | None = Query(
        default=None, description="Start time filter (defaults to 24 hours ago)"
    ),
    end: datetime | None = Query(default=None, description="End time filter"),
    limit: int = Query(default=100, ge=1, le=1000, description="Max results"),
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> ListVisionRuleEventsResponse:
    """
    List vision rule events.

    Returns rule events ordered by triggered_at descending.
    Defaults to the past 24 hours if no start time is provided.

    Path Parameters:
    - account_name: Account identifier

    Query Parameters:
    - rule_id (optional): Filter by rule
    - entity_id (optional): Filter by entity
    - start (optional): Filter events triggered after this time (default: 24h ago)
    - end (optional): Filter events triggered before this time
    - limit (optional): Max results (default 100, max 1000)
    """
    _ = context
    effective_start = (
        start if start is not None else datetime.now(timezone.utc) - timedelta(hours=24)
    )
    return await _vision_rule_events.list_rule_events(
        session=session,
        account_name=account_name,
        rule_id=rule_id,
        entity_id=entity_id,
        start=effective_start,
        end=end,
        limit=limit,
    )


@operation_router.get(
    "/accounts/{account_name}/rule-events/{event_id}",
    response_model=VisionRuleEventResponse,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_rule_event(
    account_name: str,
    event_id: uuid.UUID,
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> VisionRuleEventResponse:
    """
    Get a vision rule event by ID.

    Path Parameters:
    - account_name: Account identifier
    - event_id: UUID of the rule event
    """
    _ = context
    return await _vision_rule_events.get_rule_event(
        session=session,
        event_id=event_id,
        account_name=account_name,
    )


@operation_router.delete(
    "/accounts/{account_name}/rule-events/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def delete_rule_event(
    account_name: str,
    event_id: uuid.UUID,
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> None:
    """
    Delete a vision rule event.

    Path Parameters:
    - account_name: Account identifier
    - event_id: UUID of the rule event
    """
    _ = context
    return await _vision_rule_events.delete_rule_event(
        session=session,
        event_id=event_id,
        account_name=account_name,
    )
