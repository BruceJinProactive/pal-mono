import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.orm import Session

import db
from api.routes.admin._auth import authenticate_user
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
from api.schemas.error.error import ErrorResponse
from db.tables.types import CheckStatus
from services.auth_types import UserContext

from . import _checklist, _checkpoint, _implementation

operation_router = APIRouter(prefix=endpoints.OPERATION, tags=["Operation"])


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
    context: UserContext = Depends(authenticate_user),
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
    context: UserContext = Depends(authenticate_user),
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
    context: UserContext = Depends(authenticate_user),
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
    context: UserContext = Depends(authenticate_user),
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
    context: UserContext = Depends(authenticate_user),
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
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> None:
    """
    Delete a checklist by ID.
    """
    await _checklist.delete_checklist(checklist_id, context, session)


@operation_router.get("/checklists/{checklist_id}/checkpoints")
async def list_checklist_checkpoints(
    checklist_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
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
    context: UserContext = Depends(authenticate_user),
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
    context: UserContext = Depends(authenticate_user),
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


@operation_router.delete(
    "/checkpoints/runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_checkpoint_run(
    run_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> None:
    """
    Delete a checkpoint run by run ID.

    Deletes a single checkpoint run identified by its run_id.

    Path Parameters:
    - run_id (required): UUID of the checkpoint run to delete

    Returns:
    - 204 No Content on success

    Authorization: Via checkpoint → project → account
    """
    return await _checkpoint.delete_checkpoint_run(run_id, context, session)


@operation_router.delete(
    "/checkpoints/submissions/{submission_id}/runs",
    status_code=status.HTTP_200_OK,
)
async def delete_checkpoint_runs_by_submission(
    submission_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> dict:
    """
    Delete all checkpoint runs for a given submission ID.

    Deletes all checkpoint runs that belong to the specified submission.
    This is useful for bulk deletion when you want to remove all runs
    from a batch comparison.

    Path Parameters:
    - submission_id (required): UUID of the submission

    Returns:
    - message: Success message
    - submission_id: The submission ID
    - deleted_count: Number of runs deleted

    Example response:
    {
      "message": "Successfully deleted 15 checkpoint run(s)",
      "submission_id": "123e4567-e89b-12d3-a456-426614174000",
      "deleted_count": 15
    }

    Authorization: Via checkpoint → project → account
    """
    return await _checkpoint.delete_checkpoint_runs_by_submission(
        submission_id, context, session
    )
