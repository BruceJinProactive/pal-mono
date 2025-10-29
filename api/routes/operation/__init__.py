import uuid

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.orm import Session

import db
from api.routes.admin._auth import authenticate_user
from api.routes.admin._utils import UserContext
from api.routes.endpoints import endpoints
from api.schemas.admin.checklist import (
    Checklist,
    ChecklistCheckpointStatusResponse,
    CreateChecklistRequest,
    ListChecklistsResponse,
    UpdateChecklistRequest,
)
from api.schemas.admin.checkpoint import (
    Checkpoint,
    ListCheckpointResultsByCheckpointResponse,
    ListCheckpointResultsBySubmissionResponse,
    ListCheckpointsResponse,
)
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


@operation_router.get("/checklists/{checklist_id}/runs")
async def get_checklist_checkpoint_status(
    checklist_id: uuid.UUID,
    start_time: str = Query(
        ...,
        description="ISO 8601 timestamp for range start in user's timezone (e.g., '2025-09-17T00:00:00-07:00')",
    ),
    end_time: str = Query(
        ...,
        description="ISO 8601 timestamp for range end in user's timezone (e.g., '2025-09-17T23:59:59-07:00')",
    ),
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> ChecklistCheckpointStatusResponse:
    """
    Get checkpoint status for a checklist within a specific time range.

    Returns the status of all active checkpoints that existed before the end of the time range,
    with their last run information within the specified time window or "missing" status.

    This endpoint provides a historically accurate view - only shows checkpoints
    that were created on or before the end_time and were active at that time.

    Query Parameters:
    - start_time (required): ISO 8601 timestamp with timezone (e.g., '2025-09-17T00:00:00-07:00')
    - end_time (required): ISO 8601 timestamp with timezone (e.g., '2025-09-17T23:59:59.999999-07:00')

    Response includes:
    - checklist_id: The checklist UUID
    - start_time: The start of the time range queried
    - end_time: The end of the time range queried
    - checkpoints: List of checkpoint statuses with:
      - checkpoint_id: The checkpoint UUID
      - last_run: Run details (status, result, timestamps) or {status: "missing"}
    - summary: Statistics (total, with_runs, missing_runs)
    ```
    """
    return await _checklist.get_checklist_checkpoint_status(
        checklist_id, start_time, end_time, context, session
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
