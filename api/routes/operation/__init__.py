import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.orm import Session

import db
from api.routes.admin._auth import authenticate_user
from api.routes.admin._utils import UserContext
from api.routes.endpoints import endpoints
from api.schemas.admin.camera import (
    AnalyzeImageRequest,
    AnalyzeImageResponse,
    GetCamerasResponse,
    ImageMetadata,
    UploadBaseImageResponse,
)
from api.schemas.admin.checklist import (
    BatchChecklistHistoryResponse,
    Checklist,
    ChecklistHistoryResponse,
    CreateChecklistRequest,
    ListChecklistsResponse,
    UpdateChecklistRequest,
)
from api.schemas.admin.checkpoint import (
    Checkpoint,
    ListCheckpointResultsByCheckpointResponse,
    ListCheckpointResultsBySubmissionResponse,
    ListCheckpointsResponse,
    RecordCheckpointRunResponse,
    UpdateCheckpointRunReviewRequest,
)
from api.schemas.error.error import ErrorResponse
from db.tables.types import CheckStatus

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


@operation_router.post(
    "/accounts/{account_id}/projects/{project_id}/cameras/{camera_name}/base-image",
    response_model=UploadBaseImageResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def upload_base_image(
    account_id: str,
    project_id: str,
    camera_name: str,
    image: UploadFile = File(...),
    prompt: str = Form(...),
    context: UserContext = Depends(authenticate_user),
) -> UploadBaseImageResponse:
    """
    Upload a base reference image and initialize GPT conversation.

    This endpoint allows the frontend to upload a base reference image that will be used
    for future comparisons. The image and the initialization prompt are sent to GPT,
    and the conversation state is stored for later analysis calls.

    Path Parameters:
    - account_id: The account ID
    - project_id: The project ID
    - camera_name: The camera name/ID

    Request Body (multipart/form-data):
    - image (required): The base reference image file
    - prompt (required): The initialization prompt to send with the base image

    Returns:
    - message: Success message
    - conversation_id: Unique conversation ID for this camera
    - base_image_url: S3 URL of the uploaded base image
    - gpt_response: GPT's acknowledgment of the base image
    """
    return await _implementation.upload_base_image_handler(
        account_id, project_id, camera_name, image, prompt, context
    )


@operation_router.post(
    "/accounts/{account_id}/projects/{project_id}/cameras/{camera_name}/analyze",
    response_model=AnalyzeImageResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def analyze_camera_image(
    account_id: str,
    project_id: str,
    camera_name: str,
    request: AnalyzeImageRequest,
    context: UserContext = Depends(authenticate_user),
) -> AnalyzeImageResponse:
    """
    Analyze the current camera image against the base reference image.

    This endpoint retrieves the latest camera image (camera_name.png) and analyzes it
    using GPT, comparing it against the previously uploaded base reference image.
    The analysis is added to the existing conversation thread.

    Path Parameters:
    - account_id: The account ID
    - project_id: The project ID
    - camera_name: The camera name/ID

    Request Body (JSON):
    - prompt: Custom analysis prompt to send with the current image

    Returns:
    - conversation_id: Conversation ID used for analysis
    - analysis: GPT's analysis response
    - image_analyzed: Filename of the image that was analyzed
    - timestamp: ISO 8601 timestamp of when the analysis was performed
    """
    return await _implementation.analyze_camera_image_handler(
        account_id, project_id, camera_name, request.prompt, context
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
    checklist_id: uuid.UUID | None = Form(None),
    unassign_checklist: bool = Form(False),
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
    - checklist_id (optional): UUID - Assign checkpoint to a checklist
    - unassign_checklist (optional): boolean - Set to true to remove checkpoint from checklist (sets checklist_id to null)
    - image (optional): New image file to replace existing one

    If an image is provided, the old image will be deleted from S3 and replaced with the new one.
    Note: If unassign_checklist is true, it takes precedence over checklist_id.
    """
    return await _checkpoint.update_checkpoint(
        checkpoint_id,
        name,
        description,
        is_active,
        group,
        rules,
        checklist_id,
        unassign_checklist,
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
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> ListCheckpointResultsByCheckpointResponse:
    """
    List all checkpoint results for a specific checkpoint.

    This endpoint returns all comparison results for a given checkpoint,
    useful for viewing the history of all submissions tested against this checkpoint.

    Returns:
    - results: List of all checkpoint results
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
          "created_at": "2025-10-15T12:34:56Z",
          "updated_at": "2025-10-15T12:35:10Z"
        }
      ],
      "total": 1
    }
    """
    return await _checkpoint.list_checkpoint_results_by_checkpoint(
        checkpoint_id, context, session
    )


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
