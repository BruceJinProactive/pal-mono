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


class SnapshotResponse(BaseModel):
    """Agent config snapshot for a given fingerprint."""

    model_config = ConfigDict(from_attributes=True)

    fingerprint: str = Field(
        ..., description="SHA-256 hex fingerprint of the agent config"
    )
    agent_id: uuid.UUID = Field(..., description="Agent this snapshot belongs to")
    project_id: uuid.UUID = Field(..., description="Project this snapshot belongs to")
    system_prompt_hash: str = Field(
        ..., description="SHA-256 hash of the system prompt text alone"
    )
    system_prompt_text: str = Field(
        ..., description="Full system prompt text at time of snapshot"
    )
    config_snapshot: dict[str, Any] = Field(
        default_factory=dict,
        description="Complete agent configuration dictionary at time of snapshot",
    )
    first_seen_at: datetime.datetime = Field(
        ..., description="When this fingerprint was first recorded"
    )
    last_seen_at: datetime.datetime = Field(
        ..., description="When this fingerprint was last seen in use"
    )


class SnapshotDiffResponse(BaseModel):
    """Diff result between two agent config snapshots."""

    from_fingerprint: str = Field(
        ..., description="Fingerprint of the baseline snapshot"
    )
    to_fingerprint: str = Field(..., description="Fingerprint of the target snapshot")
    prompt_changed: bool = Field(
        ..., description="Whether the system prompt text differs"
    )
    config_changed: bool = Field(..., description="Whether the config snapshot differs")
    prompt_diff: str = Field(
        ...,
        description="Unified text diff of system_prompt_text (empty string if unchanged)",
    )
    config_diff: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of JSON path changes in config_snapshot: {path, from, to}",
    )
