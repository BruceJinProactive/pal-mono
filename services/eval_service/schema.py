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


class EvalScenario(BaseModel):
    scenario_id: str
    scenario: str
    test_category: str
    persona: str = "standard_customer"
    max_turns: int = Field(default=14, ge=1)
    user_turns: list[str | UserTurn]
    expected_tool_calls: list[ExpectedToolCall] = Field(default_factory=list)
    expected_outcomes: ExpectedOutcomes = Field(default_factory=ExpectedOutcomes)
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
