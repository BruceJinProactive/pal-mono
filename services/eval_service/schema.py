from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TurnType(str, Enum):
    STATIC = "static"
    AI_DRIVEN = "ai_driven"


class UserTurn(BaseModel):
    text: str | None = None
    type: TurnType = TurnType.STATIC
    goal: str | None = None


class ExpectedToolCall(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    optional: bool = False


class ExpectedOutcomes(BaseModel):
    task_completed: bool | None = None
    hallucination: bool | None = None


class ToolTimingConstraint(BaseModel):
    tool: str
    must_precede: str | None = None
    must_follow: str | None = None
    requires_params: list[str] = Field(default_factory=list)


class OutputUseConstraint(BaseModel):
    tool: str
    on_success: str | None = None
    on_error: str | None = None


class ExpectedProcess(BaseModel):
    tool_timing: list[ToolTimingConstraint] = Field(default_factory=list)
    output_use: list[OutputUseConstraint] = Field(default_factory=list)


class EvalScenario(BaseModel):
    scenario_id: str
    scenario: str
    test_category: str
    persona: str = "standard_customer"
    max_turns: int = Field(default=14, ge=1)
    user_turns: list[str | UserTurn]
    expected_tool_calls: list[ExpectedToolCall] = Field(default_factory=list)
    expected_outcomes: ExpectedOutcomes = Field(default_factory=ExpectedOutcomes)
    expected_process: ExpectedProcess | None = None
    context: list[str] = Field(default_factory=list)


class EvalRunRequest(BaseModel):
    project_id: str
    driver: str = "http"
    triggered_by: str = "api"


class EvalRunResponse(BaseModel):
    run_id: str
    status: str


class ScorecardResponse(BaseModel):
    project_id: str
    metrics: list[dict[str, Any]]
