"""Eval API request schemas."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field


class RunEvalRequest(BaseModel):
    """Request to trigger an evaluation run for a project."""

    project_id: uuid.UUID = Field(..., description="Project to evaluate")
    account_id: uuid.UUID = Field(..., description="Account that owns the project")
    driver: Literal["http", "direct"] = Field(
        default="http",
        description="Driver mode: http (real system) or direct (in-process)",
    )
    triggered_by: str = Field(
        default="api",
        max_length=20,
        description="Who triggered the run",
    )
