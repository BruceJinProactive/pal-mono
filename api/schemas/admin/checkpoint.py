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
