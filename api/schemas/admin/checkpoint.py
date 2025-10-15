from uuid import UUID

from pydantic import BaseModel, Field


class CreateCheckpointRequest(BaseModel):
    """Create Checkpoint Request Model"""

    project_id: UUID
    name: str
    description: str | None = None
    is_active: bool = Field(default=False)
    group: str | None = None
    rules: list[str] | None = Field(default=None)


class UpdateCheckpointRequest(BaseModel):
    """Update Checkpoint Request Model - all fields are optional"""

    name: str | None = None
    description: str | None = None
    is_active: bool | None = None
    group: str | None = None
    rules: list[str] | None = None


class Checkpoint(BaseModel):
    """Checkpoint Model"""

    id: str
    project_id: str
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
