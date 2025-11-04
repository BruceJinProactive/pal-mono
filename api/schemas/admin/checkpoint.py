from uuid import UUID

from pydantic import BaseModel, Field


class CreateCheckpointRequest(BaseModel):
    """Create Checkpoint Request Model"""

    project_id: UUID
    checklist_id: UUID | None = None
    name: str
    description: str | None = None
    is_active: bool = Field(default=False)
    group: str | None = None
    rules: list[str] | None = Field(default=None)
    requires_image: bool = Field(default=False)


class UpdateCheckpointRequest(BaseModel):
    """Update Checkpoint Request Model - all fields are optional"""

    name: str | None = None
    description: str | None = None
    is_active: bool | None = None
    group: str | None = None
    rules: list[str] | None = None
    checklist_id: UUID | None = None
    unassign_checklist: bool = False
    requires_image: bool | None = None
    remove_image: bool = False


class Checkpoint(BaseModel):
    """Checkpoint Model"""

    id: str
    project_id: str
    checklist_id: str | None
    name: str
    description: str | None
    image_url: str | None
    is_active: bool
    group: str | None
    rules: list[str] | None
    requires_image: bool


class ListCheckpointsResponse(BaseModel):
    """List Checkpoints Response Model"""

    checkpoints: list[Checkpoint]
    total: int


class CheckpointResult(BaseModel):
    """Checkpoint Result Model"""

    id: str
    checkpoint_id: str
    submission_id: str
    result: dict
    status: str
    review: str | None = None
    reviewer: str | None = None
    is_reviewed: bool = False
    created_at: str
    updated_at: str | None


class ListCheckpointResultsBySubmissionResponse(BaseModel):
    """List Checkpoint Results Grouped by Submission ID Response Model"""

    results: dict[str, list[CheckpointResult]]
    total_submissions: int


class ListCheckpointResultsByCheckpointResponse(BaseModel):
    """List Checkpoint Results by Checkpoint ID Response Model"""

    results: list[CheckpointResult]
    total: int


class RecordCheckpointRunResponse(BaseModel):
    """Response after recording a checkpoint run"""

    run_id: str = Field(..., description="The created run ID")
    checkpoint_id: str = Field(..., description="Checkpoint ID")
    status: str = Field(..., description="Status recorded")
    image_url: str | None = Field(
        None, description="Presigned S3 URL of uploaded image (null if no image)"
    )


class UpdateCheckpointRunReviewRequest(BaseModel):
    """Request model for updating review fields of a checkpoint run"""

    review: str | None = Field(None, description="Review comments/notes")
    reviewer: str | None = Field(None, description="Name or email of reviewer")
    is_reviewed: bool | None = Field(
        None, description="Whether the run has been reviewed"
    )
