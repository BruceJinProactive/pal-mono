from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CreateChecklistRequest(BaseModel):
    """Request model for creating a new checklist"""

    project_id: uuid.UUID | None = Field(
        None, description="Optional project ID to associate with the checklist"
    )
    name: str = Field(..., description="Name of the checklist", min_length=1)
    description: str | None = Field(None, description="Description of the checklist")
    ai_enabled: bool = Field(
        False, description="Whether AI is enabled for this checklist"
    )


class UpdateChecklistRequest(BaseModel):
    """Request model for updating a checklist"""

    name: str | None = Field(None, description="Name of the checklist", min_length=1)
    description: str | None = Field(None, description="Description of the checklist")
    ai_enabled: bool | None = Field(
        None, description="Whether AI is enabled for this checklist"
    )


class Checklist(BaseModel):
    """Response model for a checklist"""

    id: str = Field(..., description="Unique identifier for the checklist")
    project_id: str | None = Field(
        None, description="Project ID associated with the checklist"
    )
    name: str = Field(..., description="Name of the checklist")
    description: str | None = Field(None, description="Description of the checklist")
    ai_enabled: bool = Field(..., description="Whether AI is enabled")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime | None = Field(None, description="Last update timestamp")

    class Config:
        from_attributes = True


class ListChecklistsResponse(BaseModel):
    """Response model for listing checklists"""

    checklists: list[Checklist] = Field(..., description="List of checklists")
    total: int = Field(..., description="Total number of checklists")


class CheckpointLastRunSummary(BaseModel):
    """Summary of the last checkpoint run (compact version with only essential fields)"""

    status: str = Field(
        ...,
        description="Status of the run: 'active', 'failed', 'processing', 'error', or 'missing'",
    )
    result: dict | None = Field(
        None,
        description="Result object with overall_result and summary (null if missing)",
    )
    created_at: str | None = Field(
        None, description="ISO 8601 timestamp when run was created (null if missing)"
    )
    updated_at: str | None = Field(
        None, description="ISO 8601 timestamp when run was updated (null if missing)"
    )


class CheckpointStatusItem(BaseModel):
    """Checkpoint with its last run status"""

    checkpoint_id: str = Field(..., description="Unique identifier for the checkpoint")
    last_run: CheckpointLastRunSummary = Field(
        ..., description="Last run details or missing status"
    )


class ChecklistCheckpointStatusSummary(BaseModel):
    """Summary statistics for checkpoint status"""

    total_checkpoints: int = Field(
        ..., description="Total number of active checkpoints that existed on this date"
    )
    with_runs: int = Field(..., description="Number of checkpoints with runs")
    missing_runs: int = Field(..., description="Number of checkpoints without runs")


class ChecklistCheckpointStatusResponse(BaseModel):
    """Response model for checklist checkpoint status"""

    checklist_id: str = Field(..., description="Unique identifier for the checklist")
    start_time: str = Field(
        ...,
        description="Start of time range queried (ISO 8601 timestamp with timezone)",
    )
    end_time: str = Field(
        ..., description="End of time range queried (ISO 8601 timestamp with timezone)"
    )
    checkpoints: list[CheckpointStatusItem] = Field(
        ..., description="List of checkpoints with their last run status"
    )
    summary: ChecklistCheckpointStatusSummary = Field(
        ..., description="Summary statistics"
    )
