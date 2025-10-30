import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.orm import Session

import db
from api.routes.admin._auth import authenticate_user
from api.routes.admin._utils import UserContext
from api.routes.endpoints import endpoints
from api.schemas.admin.camera import GetCamerasResponse
from api.schemas.admin.checklist import (
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


@operation_router.get("/checklists/{checklist_id}/history")
async def get_checklist_history(
    checklist_id: uuid.UUID,
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
) -> ChecklistHistoryResponse:
    """
    Get check history for a checklist within a date range.

    Returns the last run for each CURRENTLY ACTIVE checkpoint in the checklist
    within the specified date range. Checkpoints that are no longer in the
    checklist are excluded from the response.

    Query parameters:
    - checklist_id (path): UUID of the checklist
    - start_date (required): ISO 8601 timestamp with timezone
    - end_date (required): ISO 8601 timestamp with timezone

    Returns:
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

    Authorization: Via checklist → project → account
    """
    return await _checklist.get_checklist_history(
        checklist_id, start_date, end_date, context, session
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

    Query parameters:
    - project_id (required): Project ID to filter checkpoint results
    - status (optional): Filter results by status (processing, active, failed)

    Returns:
    - results: Dictionary mapping submission_id to list of checkpoint results
    - total_submissions: Total number of unique submissions

    Example response:
    {
      "results": {
        "submission-uuid-1": [result1, result2],
        "submission-uuid-2": [result3]
      },
      "total_submissions": 2
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
