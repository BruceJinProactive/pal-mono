"""Eval API response schemas."""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EvalRunResponse(BaseModel):
    """Response for a single eval run."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    status: str
    driver_mode: str | None = None
    triggered_by: str | None = None
    scenario_count: int | None = None
    passed_count: int | None = None
    failed_count: int | None = None
    overall_score: float | None = None
    error_message: str | None = None
    started_at: datetime.datetime | None = None
    completed_at: datetime.datetime | None = None
    created_at: datetime.datetime | None = None


class EvalResultResponse(BaseModel):
    """Response for a single eval result."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    eval_run_id: uuid.UUID
    scenario_id: str | None = None
    metric_name: str | None = None
    score: float | None = None
    passed: bool | None = None
    reason: str | None = None
    raw_output: dict[str, Any] | None = None


class EvalRunWithResultsResponse(BaseModel):
    """Eval run with its results."""

    run: EvalRunResponse
    results: list[EvalResultResponse] = Field(default_factory=list)


class ScorecardResponse(BaseModel):
    """Aggregated scorecard for a project."""

    project_id: str
    runs: list[dict[str, Any]] = Field(default_factory=list)
