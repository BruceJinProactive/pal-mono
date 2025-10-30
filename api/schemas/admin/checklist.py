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


class CheckpointRunDetail(BaseModel):
    """Detail of the last checkpoint run"""

    run_id: str = Field(..., description="Run ID")
    status: str = Field(..., description="Status: done or missing")
    result: dict = Field(..., description="Result data")
    created_at: str = Field(..., description="Run timestamp (ISO 8601)")
    image_url: str | None = Field(None, description="Presigned S3 URL if available")


class CheckpointHistoryItem(BaseModel):
    """Single checkpoint with its last run in the date range"""

    checkpoint_id: str = Field(..., description="Checkpoint ID")
    checkpoint_name: str = Field(..., description="Checkpoint name")
    last_run: CheckpointRunDetail | None = Field(
        None, description="Last run details, null if no run in date range"
    )


class ChecklistHistorySummary(BaseModel):
    """Summary statistics for the checklist history"""

    total_checkpoints: int = Field(..., description="Total current checkpoints")
    with_runs: int = Field(..., description="Checkpoints with runs in date range")
    missing_runs: int = Field(..., description="Checkpoints without runs in date range")


class ChecklistHistoryResponse(BaseModel):
    """Response for checklist check history"""

    checklist_id: str = Field(..., description="Checklist ID")
    start_date: str = Field(..., description="Start date (ISO 8601)")
    end_date: str = Field(..., description="End date (ISO 8601)")
    checkpoints: list[CheckpointHistoryItem] = Field(
        ..., description="Checkpoint history"
    )
    summary: ChecklistHistorySummary = Field(..., description="Summary statistics")


class BatchChecklistHistoryResponse(BaseModel):
    """Response for batch checklist check history"""

    results: list[ChecklistHistoryResponse] = Field(
        ..., description="List of checklist history responses"
    )
