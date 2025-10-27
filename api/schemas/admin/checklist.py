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
