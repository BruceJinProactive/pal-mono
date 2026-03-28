# P1-B2a: Pydantic models + YAML loader + validation

**Task:** https://www.notion.so/3318c0822e4981bab818e0fcd3bc51d8
**Type:** CODE
**Est. Hours:** 3
**Blocked by:** None

---

## Background

The eval service needs a YAML-based scenario format that FDEs can author per restaurant. This task creates the Pydantic models, YAML loader, and validation logic. The format aligns with pal-agents' existing `multi_turn_v4.json` pattern.

`services/eval_service/` does not exist yet — this is the first file created there.

---

## Implementation Steps

- [ ] **Step 1: Create `services/eval_service/__init__.py`**

  Empty or minimal exports. Follow pattern from other services.

- [ ] **Step 2: Create `services/eval_service/schema.py`**

  Pydantic models:
  ```python
  from pydantic import BaseModel, Field
  from typing import Any
  from enum import Enum

  class TurnType(str, Enum):
      STATIC = "static"
      AI_DRIVEN = "ai_driven"

  class UserTurn(BaseModel):
      text: str | None = None
      type: TurnType = TurnType.STATIC
      goal: str | None = None  # required when type=ai_driven

  class ExpectedToolCall(BaseModel):
      tool: str
      args: dict[str, Any] = Field(default_factory=dict)

  class ExpectedOutcomes(BaseModel):
      task_completed: bool | None = None
      hallucination: bool | None = None

  class EvalScenario(BaseModel):
      scenario_id: str
      scenario: str  # description
      test_category: str
      persona: str = "standard_customer"
      user_turns: list[str | UserTurn]
      expected_tool_calls: list[ExpectedToolCall] = Field(default_factory=list)
      expected_outcomes: ExpectedOutcomes = Field(default_factory=ExpectedOutcomes)
      context: list[str] = Field(default_factory=list)

  class EvalRunRequest(BaseModel):
      project_id: str
      driver: str = "http"  # "http" | "direct"
      triggered_by: str = "api"

  class EvalRunResponse(BaseModel):
      run_id: str
      status: str

  class ScorecardResponse(BaseModel):
      project_id: str
      metrics: list[dict[str, Any]]
  ```

- [ ] **Step 3: Create `services/eval_service/_scenario_loader.py`**

  ```python
  import yaml
  from pathlib import Path
  from .schema import EvalScenario

  SCENARIOS_DIR = Path(__file__).parent / "scenarios"

  def validate_scenarios_from_yaml(yaml_path: str | Path) -> list[EvalScenario]:
      """Validate and parse a YAML scenario file."""

  def load_scenarios(project_id: str | None = None) -> list[EvalScenario]:
      """Load generic + per-project scenarios."""
  ```

- [ ] **Step 4: Write unit tests**

  File: `tests/services/eval_service/test_scenario_loader.py`
  - Valid YAML parses correctly
  - Missing required fields raise validation error
  - Malformed YAML raises clear error
  - AI-driven turns require `goal` field

---

## Validation

```bash
uv run pytest tests/services/eval_service/test_scenario_loader.py -v
./scripts/validate.sh
```

---

## Risks & Open Questions

- YAML format may need iteration once FDEs start authoring — keep the schema flexible with optional fields
- `pyyaml` should already be a dependency — verify in pyproject.toml
