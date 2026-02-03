import uuid
from datetime import date, datetime
from typing import Annotated
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
    CompareCameraCheckpointResponse,
    GetCameraImageUrlsResponse,
    GetCamerasResponse,
    ImageMetadata,
)
from api.schemas.admin.checklist import (
    BatchChecklistHistoryResponse,
    Checklist,
    CreateChecklistRequest,
    ListChecklistsResponse,
    UpdateChecklistRequest,
)
from api.schemas.admin.checkpoint import (
    Checkpoint,
    CheckpointResult,
    ListCheckpointResultsByCheckpointResponse,
    ListCheckpointResultsBySubmissionResponse,
    ListCheckpointsResponse,
    RecordCheckpointRunResponse,
    UpdateCheckpointRunReviewRequest,
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
from db.repositories.project_repository import ProjectRepositoryAsync
from db.tables.types import CheckStatus, ExecutionStatus
from services import signal_source_service
from services.auth_service.authorization import check_permission
from services.auth_service.dependencies import (
    require_checklist_permission,
    require_execution_permission,
    require_project_permission,
    require_routine_permission,
    require_submission_permission,
)
from services.auth_types import UserContext
from utils.log import logger

from . import (
    _checklist,
    _checkpoint,
    _implementation,
    _monitoring,
    _routines,
    _signal_sources,
    _video_upload,
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


@operation_router.post(
    "/checkpoints/{checkpoint_id}/compare-camera",
    response_model=CompareCameraCheckpointResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def compare_camera_checkpoint(
    checkpoint_id: str,
    start_time: str = Query(
        ...,
        description="Start time in ISO 8601 format (e.g., 2025-11-05T10:00:00Z)",
    ),
    end_time: str = Query(
        ...,
        description="End time in ISO 8601 format (e.g., 2025-11-05T12:00:00Z)",
    ),
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> CompareCameraCheckpointResponse:
    """
    Compare camera images against a specific checkpoint.

    Retrieves images from S3 within the specified time range and compares each image
    against the checkpoint's reference image and rules using AI. The camera name is
    derived from the checkpoint's name field.

    **Process:**
    1. Fetches checkpoint by checkpoint_id
    2. Retrieves all camera images from S3 within time range (using checkpoint.name as camera_name)
    3. Creates checkpoint runs with status="processing" immediately
    4. Returns response with run IDs
    5. Processes comparisons in background (using checkpoint's image and rules)
    6. Updates runs with results asynchronously

    **Query Results:**
    - All runs share the same submission_id (use to query batch results)
    - Individual runs can be queried by checkpoint_run_id
    - Results are stored in checkpoint_runs table with comparison details

    **Requirements:**
    - Checkpoint must exist
    - Checkpoint must have reference image and rules configured
    - Time range should be < 24 hours for optimal performance

    **Example:**
    ```
    POST /checkpoints/123e4567-e89b-12d3-a456-426614174000/compare-camera
        ?start_time=2025-11-05T10:00:00Z
        &end_time=2025-11-05T12:00:00Z
    ```

    Returns immediately with checkpoint_run_ids and submission_id to track progress.
    """
    return await _checkpoint.compare_camera_checkpoint_handler(
        context=context,
        session=session,
        checkpoint_id=checkpoint_id,
        start_time=start_time,
        end_time=end_time,
    )


"""
---------- Checklist Endpoints ----------
-----------------------------------------
"""


@operation_router.post(
    "/projects/{project_id}/checklists", status_code=status.HTTP_201_CREATED
)
async def create_checklist(
    project_id: uuid.UUID,
    checklist: CreateChecklistRequest,
    context: UserContext = Depends(
        require_project_permission("project.write", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> Checklist:
    """
    Create a new checklist for a project.
    """
    return await _checklist.create_checklist(project_id, checklist, context, session)


@operation_router.get("/checklists/history")
async def get_checklist_history(
    checklist_ids: list[uuid.UUID] = Query(
        ...,
        description="List of checklist IDs to retrieve history for",
    ),
    start_date: datetime = Query(
        ...,
        description="Start date in ISO 8601 format with timezone (e.g., 2025-01-01T00:00:00Z)",
    ),
    end_date: datetime = Query(
        ...,
        description="End date in ISO 8601 format with timezone (e.g., 2025-01-31T23:59:59Z)",
    ),
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> BatchChecklistHistoryResponse:
    """
    Get check history for multiple checklists within a date range.

    Returns the last run for each CURRENTLY ACTIVE checkpoint in each checklist
    within the specified date range. Checkpoints that are no longer in the
    checklist are excluded from the response.

    Query parameters:
    - checklist_ids (required): List of checklist UUIDs
    - start_date (required): ISO 8601 timestamp with timezone
    - end_date (required): ISO 8601 timestamp with timezone

    Returns:
    - results: Array of checklist history responses
      - checklist_id: The checklist ID
      - start_date: Query start date
      - end_date: Query end date
      - checkpoints: Array of checkpoint history items (current checkpoints only)
        - checkpoint_id: Checkpoint UUID
        - checkpoint_name: Checkpoint name
        - last_run: Last run details or null if no run in date range
          - run_id: Run UUID
          - status: "done" or "missing"
          - result: Result JSON
          - created_at: Run timestamp
          - image_url: Presigned S3 URL if image exists
      - summary: Summary statistics
        - total_checkpoints: Total current checkpoints
        - with_runs: Count with runs in date range
        - missing_runs: Count without runs in date range
        - reviewed_runs: Count of reviewed runs in date range
        - unreviewed_runs: Count of unreviewed runs in date range

    Authorization: Via checklist → project → account
    """
    return await _checklist.get_batch_checklist_history(
        checklist_ids, start_date, end_date, context, session
    )


@operation_router.get("/checklists/{checklist_id}")
async def get_checklist(
    checklist_id: uuid.UUID,
    context: UserContext = Depends(
        require_checklist_permission("account.read", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> Checklist:
    """
    Get a checklist by ID.
    """
    return await _checklist.get_checklist(checklist_id, context, session)


@operation_router.get("/projects/{project_id}/checklists")
async def list_project_checklists(
    project_id: uuid.UUID,
    exclude: uuid.UUID | None = Query(
        None, description="Optional checklist ID to exclude from results"
    ),
    context: UserContext = Depends(
        require_project_permission("project.read", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> ListChecklistsResponse:
    """
    Retrieve a list of checklists for the specified project.
    Optionally exclude a specific checklist by ID.
    """
    return await _checklist.list_checklists_by_project(
        project_id, context, session, exclude
    )


@operation_router.patch("/checklists/{checklist_id}")
async def update_checklist(
    checklist_id: uuid.UUID,
    update_request: UpdateChecklistRequest,
    context: UserContext = Depends(
        require_checklist_permission("account.write", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> Checklist:
    """
    Update a checklist by ID.
    """
    return await _checklist.update_checklist(
        checklist_id, update_request, context, session
    )


@operation_router.delete(
    "/checklists/{checklist_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_checklist(
    checklist_id: uuid.UUID,
    context: UserContext = Depends(
        require_checklist_permission("account.write", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> None:
    """
    Delete a checklist by ID.
    """
    await _checklist.delete_checklist(checklist_id, context, session)


@operation_router.get("/checklists/{checklist_id}/checkpoints")
async def list_checklist_checkpoints(
    checklist_id: uuid.UUID,
    context: UserContext = Depends(
        require_checklist_permission("account.read", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> ListCheckpointsResponse:
    """
    Retrieve a list of checkpoints for the specified checklist.
    """
    return await _checkpoint.list_checkpoints_by_checklist(
        checklist_id, context, session
    )


"""
---------- Checkpoint Endpoints ----------
------------------------------------------
"""


@operation_router.get("/projects/{project_id}/checkpoints")
async def list_checkpoints(
    project_id: uuid.UUID,
    context: UserContext = Depends(
        require_project_permission("project.read", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> ListCheckpointsResponse:
    """
    List all checkpoints for a project.
    """
    return await _checkpoint.list_checkpoints(project_id, context, session)


@operation_router.post(
    "/projects/{project_id}/checkpoints", status_code=status.HTTP_201_CREATED
)
async def create_checkpoint(
    project_id: uuid.UUID,
    checklist_id: uuid.UUID | None = Form(None),
    name: str = Form(...),
    description: str | None = Form(None),
    is_active: bool = Form(False),
    group: str | None = Form(None),
    rules: str | None = Form(None),
    requires_image: bool = Form(False),
    image: UploadFile | None = File(None),
    context: UserContext = Depends(
        require_project_permission("project.write", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> Checkpoint:
    """
    Create a new checkpoint with an optional image upload.

    Request body (multipart/form-data):
    - checklist_id (optional): UUID - Checklist ID this checkpoint belongs to
    - name (required): string - Checkpoint name
    - description (optional): string - Checkpoint description
    - is_active (optional, default: false): boolean - Whether checkpoint is active
    - group (optional): string - Checkpoint group
    - rules (optional): JSON array string of rules (e.g., '["rule1", "rule2"]')
    - image (optional): Image file

    The image will be uploaded to S3 and the URL will be stored in the checkpoint.
    """
    return await _checkpoint.create_checkpoint(
        project_id,
        checklist_id,
        name,
        description,
        is_active,
        group,
        rules,
        requires_image,
        image,
        context,
        session,
    )


@operation_router.patch("/checkpoints/{checkpoint_id}", status_code=status.HTTP_200_OK)
async def update_checkpoint(
    checkpoint_id: uuid.UUID,
    name: str | None = Form(None),
    description: str | None = Form(None),
    is_active: bool | None = Form(None),
    group: str | None = Form(None),
    rules: str | None = Form(None),
    requires_image: bool | None = Form(None),
    checklist_id: uuid.UUID | None = Form(None),
    unassign_checklist: bool = Form(False),
    remove_image: bool = Form(False),
    image: UploadFile | None = File(None),
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> Checkpoint:
    """
    Update a checkpoint by ID. All fields are optional.
    If a new image is provided, it will replace the old one.

    Request body (multipart/form-data):
    - name (optional): string - New checkpoint name
    - description (optional): string - New checkpoint description
    - is_active (optional): boolean - New active status
    - group (optional): string - New checkpoint group
    - rules (optional): JSON array string of rules (e.g., '["rule1", "rule2"]')
    - requires_image (optional): boolean - Whether checkpoint requires an image
    - checklist_id (optional): UUID - Assign checkpoint to a checklist
    - unassign_checklist (optional): boolean - Set to true to remove checkpoint from checklist (sets checklist_id to null)
    - remove_image (optional): boolean - Set to true to remove the checkpoint image (takes precedence over image)
    - image (optional): New image file to replace existing one

    If an image is provided, the old image will be deleted from S3 and replaced with the new one.
    Note: If unassign_checklist is true, it takes precedence over checklist_id.
    Note: If remove_image is true, it takes precedence over image upload.
    """
    return await _checkpoint.update_checkpoint(
        checkpoint_id,
        name,
        description,
        is_active,
        group,
        rules,
        requires_image,
        checklist_id,
        unassign_checklist,
        remove_image,
        image,
        context,
        session,
    )


@operation_router.delete(
    "/checkpoints/{checkpoint_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_checkpoint(
    checkpoint_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> None:
    """
    Delete a checkpoint by ID.

    The checkpoint will be permanently deleted from the database.
    """
    return await _checkpoint.delete_checkpoint(checkpoint_id, context, session)


@operation_router.post(
    "/checkpoints/{checkpoint_id}/compare", status_code=status.HTTP_200_OK
)
async def compare_checkpoint(
    checkpoint_id: uuid.UUID,
    image: UploadFile = File(...),
    submission_id: str = Form(None),
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> dict:
    """
    Compare an uploaded image with a checkpoint's image (async processing).

    This endpoint immediately returns a 200 response with 'processing' status.
    The actual AI comparison runs in the background and updates the database.

    Request body (multipart/form-data):
    - image (required): Image file to compare
    - submission_id (optional): Submission UUID generated by frontend

    Returns immediately:
    - checkpoint_result_id: UUID to check result status
    - checkpoint_id: The checkpoint being compared against
    - submission_id: The submission ID (provided or auto-generated)
    - status: "processing"
    - message: Instructions to check result

    Use GET /checkpoints/results/{checkpoint_result_id} to check the result.
    """
    return await _checkpoint.compare_checkpoint(
        checkpoint_id, image, context, session, submission_id
    )


@operation_router.post("/checkpoints/runs", status_code=status.HTTP_201_CREATED)
async def record_checkpoint_run(
    checkpoint_id: uuid.UUID = Form(...),
    status: str = Form(..., pattern="^(done|missing)$"),
    image: UploadFile | None = File(None),
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> RecordCheckpointRunResponse:
    """
    Record a checkpoint run with a simple status and optional image.

    Creates a new run record for a checkpoint with status "done" or "missing".
    Optionally upload an image that will be stored in S3.

    Request body (multipart/form-data):
    - checkpoint_id (required): UUID - The checkpoint ID
    - status (required): string - Either "done" or "missing"
    - image (optional): Image file (jpg/png)

    Response:
    - run_id: UUID of the created run
    - checkpoint_id: The checkpoint ID
    - status: The status that was recorded
    - image_url: S3 file path of uploaded image (null if no image)

    The uploaded image will be stored at:
    checkpoint_runs/{project_id}/{checkpoint_id}/{run_id}.{jpg|png}
    """
    return await _checkpoint.record_checkpoint_run(
        checkpoint_id, status, image, context, session
    )


@operation_router.get("/checkpoints/results", status_code=status.HTTP_200_OK)
async def list_checkpoint_results_by_submission(
    project_id: uuid.UUID = Query(
        ...,
        description="Required project ID to filter checkpoint results",
    ),
    status_param: CheckStatus | None = Query(
        None,
        description="Optional filter by status (processing, active, failed)",
        alias="status",
    ),
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> ListCheckpointResultsBySubmissionResponse:
    """
    List all checkpoint results grouped by submission_id for a specific project.

    This endpoint returns checkpoint results filtered by the required project_id,
    grouped by their submission_id for easy tracking of multi-checkpoint submissions.
    Each result now includes review information (review, reviewer, is_reviewed).

    Query parameters:
    - project_id (required): Project ID to filter checkpoint results
    - status (optional): Filter results by status (processing, active, failed)

    Returns:
    - results: Dictionary mapping submission_id to list of checkpoint results (with review fields)
    - total_submissions: Total number of unique submissions

    Example response:
    {
      "results": {
        "submission-uuid-1": [
          {
            "id": "run-uuid",
            "checkpoint_id": "checkpoint-uuid",
            "submission_id": "submission-uuid-1",
            "result": {...},
            "status": "active",
            "review": "Approved",
            "reviewer": "admin@example.com",
            "is_reviewed": true,
            "created_at": "2025-10-30T...",
            "updated_at": "2025-10-30T..."
          }
        ]
      },
      "total_submissions": 1
    }
    """
    return await _checkpoint.list_checkpoint_results_by_submission(
        status_param, project_id, context, session
    )


@operation_router.get(
    "/checkpoints/{checkpoint_id}/results", status_code=status.HTTP_200_OK
)
async def list_checkpoint_results_by_checkpoint(
    checkpoint_id: uuid.UUID,
    start_date: datetime | None = Query(
        None,
        description="Optional start date - filters by timestamp >= this value (ISO 8601 format with timezone, e.g., 2025-01-01T00:00:00Z)",
    ),
    end_date: datetime | None = Query(
        None,
        description="Optional end date - filters by timestamp <= this value (ISO 8601 format with timezone, e.g., 2025-01-31T23:59:59Z)",
    ),
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> ListCheckpointResultsByCheckpointResponse:
    """
    List all checkpoint results for a specific checkpoint with optional date filtering.

    This endpoint returns all comparison results for a given checkpoint,
    useful for viewing the history of all submissions tested against this checkpoint.

    Path Parameters:
    - checkpoint_id: UUID of the checkpoint

    Query Parameters:
    - start_date (optional): Filter results by timestamp >= this date (ISO 8601 format)
    - end_date (optional): Filter results by timestamp <= this date (ISO 8601 format)

    Note: Filtering uses the 'timestamp' column which represents:
    - For camera checkpoints: The actual time the image was captured (from filename)
    - For manual checkpoints: The time the checkpoint run was created

    Returns:
    - results: List of checkpoint results (filtered by date if parameters provided)
    - total: Total number of results

    Example response:
    {
      "results": [
        {
          "id": "result-uuid",
          "checkpoint_id": "checkpoint-uuid",
          "submission_id": "submission-uuid",
          "result": {"overall_result": "PASS", ...},
          "status": "active",
          "image_url": "https://s3.amazonaws.com/...",
          "created_at": "2025-10-15T12:34:56Z",
          "updated_at": "2025-10-15T12:35:10Z"
        }
      ],
      "total": 1
    }
    """
    return await _checkpoint.list_checkpoint_results_by_checkpoint(
        checkpoint_id, start_date, end_date, context, session
    )


@operation_router.get("/checkpoints/runs/{run_id}", status_code=status.HTTP_200_OK)
async def get_checkpoint_run(
    run_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> CheckpointResult:
    """
    Get a single checkpoint run by its ID.

    This endpoint returns detailed information about a specific checkpoint run,
    including presigned image URLs if the run contains images.

    Path Parameters:
    - run_id: UUID of the checkpoint run

    Returns:
    - CheckpointResult with all run details and presigned image URL

    Example response:
    {
      "id": "run-uuid",
      "checkpoint_id": "checkpoint-uuid",
      "submission_id": "submission-uuid",
      "result": {"overall_result": "PASS", ...},
      "status": "active",
      "image_url": "https://s3.amazonaws.com/...",
      "review": "Approved",
      "reviewer": "manager@example.com",
      "is_reviewed": true,
      "created_at": "2025-10-15T12:34:56Z",
      "updated_at": "2025-10-15T12:35:10Z"
    }

    Authorization: Via checkpoint → project → account
    """
    return await _checkpoint.get_checkpoint_run(run_id, context, session)


@operation_router.patch(
    "/checkpoints/runs/{run_id}/review", status_code=status.HTTP_200_OK
)
async def update_checkpoint_run_review(
    run_id: uuid.UUID,
    request: "UpdateCheckpointRunReviewRequest",
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> dict:
    """
    Update review fields (review, reviewer, is_reviewed) for a checkpoint run.

    This endpoint allows updating the review status and comments for a specific checkpoint run
    identified by its run_id. All fields are optional - only provide the fields you want to update.

    Path Parameters:
    - run_id (required): UUID of the checkpoint run to update

    Request Body:
    - review (optional): Review comments/notes
    - reviewer (optional): Name or email of the reviewer
    - is_reviewed (optional): Whether the run has been reviewed (true/false)

    Returns:
    - message: Success message
    - run_id: ID of the updated run
    - review: Updated review comment
    - reviewer: Updated reviewer
    - is_reviewed: Updated review status

    ```
    """
    return await _checkpoint.update_checkpoint_run_review_fields(
        run_id, request.review, request.reviewer, request.is_reviewed, context, session
    )


@operation_router.post("/checkpoints/runs/batch-delete", status_code=status.HTTP_200_OK)
async def batch_delete_checkpoint_runs(
    run_ids: list[uuid.UUID],
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> dict:
    """
    Delete multiple checkpoint runs by their run IDs (batch delete).

    Deletes multiple checkpoint runs identified by their run_ids.
    This is useful for bulk deletion when you want to remove specific runs.

    Request Body:
    - run_ids (required): List of UUIDs of checkpoint runs to delete

    Returns:
    - message: Success message
    - deleted_count: Number of runs deleted

    Example request:
    POST /checkpoints/runs/batch-delete
    Content-Type: application/json
    ["uuid1", "uuid2", "uuid3"]

    Example response:
    {
      "message": "Successfully deleted 15 checkpoint run(s)",
      "deleted_count": 15
    }

    Authorization: Via checkpoint → project → account
    """
    return await _checkpoint.delete_checkpoint_runs(run_ids, context, session)


@operation_router.post(
    "/checkpoints/runs/{run_id}/rerun", status_code=status.HTTP_200_OK
)
async def rerun_checkpoint_run(
    run_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> dict:
    """
    Rerun checkpoint analysis for an existing run (in-place update).

    Fetches the existing image from S3 and re-runs the OpenAI comparison.
    Updates the run in-place with new results.

    Path Parameters:
    - run_id (required): UUID of the checkpoint run to rerun

    Returns:
    - run_id: The run ID being rerun
    - status: "processing"
    - message: Instructions to poll for results

    Example request:
    POST /checkpoints/runs/123e4567-e89b-12d3-a456-426614174000/rerun

    Example response:
    {
      "run_id": "123e4567-e89b-12d3-a456-426614174000",
      "status": "processing",
      "message": "Rerun started. Poll for results using GET /checkpoints/runs/{run_id}"
    }

    Error responses:
    - 404: Run not found
    - 409: Run is already processing
    - 400: Image no longer available in storage

    Authorization: Via checkpoint → project → account
    """
    return await _checkpoint.rerun_checkpoint_run(run_id, context, session)


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
    prompt: str = Form(...),
    structured_output: str | None = Form(None),
    model: str | None = Form(None),
    enabled: bool = Form(True),
    monitoring_time_window: str | None = Form(None),
    reference_images: list[UploadFile] = File(default=[]),
    reference_image_descriptions: list[str] = Form(default=[]),
    context: UserContext = Depends(
        require_project_permission("project.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> MonitoringConfigResponse:
    """
    Create a new monitoring configuration with optional reference image uploads.

    Path Parameters:
    - project_id: UUID of the project

    Request Body (multipart/form-data):
    - signal_source_id (required): UUID of the signal source
    - name (required): Name of the monitoring config (unique per project)
    - description (optional): Description of what is being monitored
    - prompt (required): AI analysis prompt (1-2000 characters)
    - model (optional): JSON string with LLM model configuration (e.g., '{"provider": "google", "model": "gemini-3-flash-preview"}')
    - enabled (optional, default: true): Whether monitoring is active
    - monitoring_time_window (optional): JSON string with time window config (e.g., '{"enabled": true, "start_time": "06:00", "end_time": "22:00"}')
    - reference_images (optional): Multiple image files for reference
    - reference_image_descriptions (optional): Descriptions for each reference image (must match number of images)

    Returns:
    - MonitoringConfigResponse with the created config details
    """
    import json

    from api.schemas.operations.monitoring import (
        AIAnalysisRules,
        ModelConfig,
        StructuredOutputField,
    )

    _ = context  # Used by require_project_permission

    # Validate that number of images matches number of descriptions
    if len(reference_images) != len(reference_image_descriptions):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Number of images ({len(reference_images)}) must match number of descriptions ({len(reference_image_descriptions)})",
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

    # Build the request object from form fields
    rules = AIAnalysisRules(
        prompt=prompt,
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
    )

    return await _monitoring.create_monitoring_config(
        project_id=project_id,
        request=request,
        reference_images=reference_images,
        reference_image_descriptions=reference_image_descriptions,
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
    prompt: str | None = Form(None),
    structured_output: str | None = Form(None),
    model: str | None = Form(None),
    enabled: bool | None = Form(None),
    monitoring_time_window: str | None = Form(None),
    # Reference image operations (send only what changes)
    add_images: list[UploadFile] = File(default=[]),
    add_descriptions: list[str] = Form(default=[]),
    remove_image_ids: list[str] = Form(default=[]),
    update_descriptions: list[str] = Form(default=[]),
    context: UserContext = Depends(
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
    - skip_outside_business_hours: Skip image processing when captured outside business hours

    Reference Image Operations (send only what you want to change):
    - add_images: New image files to add
    - add_descriptions: Descriptions for new images (must match add_images count)
    - remove_image_ids: List of image UUIDs to remove
    - update_descriptions: JSON array of {"id": "uuid", "description": "new desc"} to update descriptions only

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
       update_descriptions=[{"id": "uuid3", "description": "updated"}]

    5. Remove all:
       remove_image_ids=[list all current image IDs]
    """
    _ = context  # Used by require_project_permission

    # Validate add operations
    if add_images and len(add_images) != len(add_descriptions):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Number of add_images ({len(add_images)}) must match "
            f"number of add_descriptions ({len(add_descriptions)})",
        )

    # Parse update_descriptions JSON
    import json

    update_desc_map: dict[str, str] = {}
    if update_descriptions:
        malformed_entries: list[dict] = []
        try:
            for idx, update_json in enumerate(update_descriptions):
                update_obj = json.loads(update_json)
                # Validate required fields
                if "id" not in update_obj or "description" not in update_obj:
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
                    update_desc_map[update_obj["id"]] = update_obj["description"]
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

    # Build request object
    request = UpdateMonitoringConfigRequest(
        name=name,
        description=description,
        prompt=prompt,
        structured_output=parsed_structured_output,
        model=parsed_model,
        enabled=enabled,
        monitoring_time_window=parsed_time_window,
    )

    return await _monitoring.update_monitoring_config(
        config_id=config_id,
        request=request,
        session=session,
        project_id=project_id,
        add_images=add_images,
        add_descriptions=add_descriptions,
        remove_image_ids=remove_image_ids,
        update_descriptions=update_desc_map,
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
    project_repo = ProjectRepositoryAsync(session)
    project = await project_repo.get_project(project_id)
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
