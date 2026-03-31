# P1-C2: Eval service — runner + evaluators + result storage

**Type:** CODE
**Est. Hours:** 20 (3 engineering days)
**Blocked by:** P1-A1 (pal-agents eval SDK — done), P1-B2 (scenario format — done), P1-C1 (DB tables — done)

---

## Background

Critical-path bottleneck of Phase 1. Wires together scenario loading (P1-B2), DB tables (P1-C1), and the pal-agents eval SDK (P1-A1) into a background-task runner that executes scenarios, runs evaluators, and writes results.

Runs in-process as a FastAPI background task. No Lambda, no SQS, no separate worker.

### Key constraint: pal-agents `evals` module availability

The installed pal-agents v0.2.206 may not have the `evals` subpackage yet. Use `try/except ImportError` for graceful degradation of E5-E8 SDK evaluators and ConversationRunner. Custom evaluators (E1-E4) and the runner scaffolding work independently.

---

## Existing Code Inventory

| File | Status | Provides |
|------|--------|----------|
| `services/eval_service/schema.py` | Done | `EvalScenario`, `EvalRunRequest`, etc. |
| `services/eval_service/_scenario_loader.py` | Done | `load_scenarios()`, `validate_scenarios_from_yaml()` |
| `services/eval_service/scenarios/generic/` | Done | 11 YAML scenario files |
| `db/repositories/eval_run_repository.py` | Done | `EvalRunRepositoryAsync` |
| `db/repositories/eval_result_repository.py` | Done | `EvalResultRepositoryAsync` |
| `db/repositories/agent_config_snapshot_repository.py` | Done | `AgentConfigSnapshotRepositoryAsync` |

---

## Files to Create

### 1. `services/eval_service/_runner.py` — Background task runner

```python
async def create_eval_run(project_id, account_id, driver_mode, triggered_by, session) -> EvalRun
def _schedule_eval_background(eval_run_id, project_id, driver_mode) -> None
async def _run_eval_background(eval_run_id, project_id, driver_mode) -> None
async def get_eval_run(run_id, session) -> EvalRun | None
async def get_eval_results(run_id, session) -> list[EvalResult]
async def get_scorecard(project_id, limit, session) -> dict
async def mark_stale_runs_failed(session) -> int
```

Session ownership: `_run_eval_background` creates own `AsyncSessionLocal()`. Error handling uses separate session for status update.

GC pattern: module-level `_background_tasks: set[asyncio.Task[object]]` with done callback.

### 2. `services/eval_service/_evaluators.py` — Evaluator orchestrator

```python
@dataclass
class EvaluatorResult: metric_name, score, passed, reason, raw_output
@dataclass
class ConversationRecord: scenario, turns, tool_calls, agent_responses

async def evaluate_scenario(record, project_context=None) -> list[EvaluatorResult]
```

Execution order: deterministic first (E1, E3), then LLM judges in parallel (E2, E4), then SDK evaluators (E5-E8).

### 3. `services/eval_service/evaluators/` — One file per custom evaluator

| File | Evaluator | Type |
|------|-----------|------|
| `tool_call.py` | E1 Tool Call Verification | Deterministic |
| `groundedness.py` | E3 Hours/Info Groundedness | Deterministic + LLM |
| `menu_hallucination.py` | E2 Menu Hallucination | LLM judge |
| `allergy_safety.py` | E4 Allergy Safety | LLM judge (zero-tolerance) |

### 4. `services/eval_service/_driver_factory.py` — AgentDriver construction

Local protocol stub until pal-agents evals module is confirmed available. Factory creates HTTPDriver or DirectDriver based on `driver_mode`.

### 5. `services/eval_service/_llm.py` — Shared LLM judge utilities

`llm_judge(system_prompt, user_prompt, model)` using Anthropic client. Retry with backoff for 429/503.

---

## Files to Modify

- `services/eval_service/__init__.py` — expand exports
- `events/schema.py` — add `EvalRunRequested` event (for future Lambda extraction)

---

## Runner Flow

```
POST /v1/eval/run (P1-C3)
  → create_eval_run() — creates EvalRun row (pending), fires background task
  → Returns 202 immediately

_run_eval_background() — owns AsyncSessionLocal
  1. Update status → 'running'
  2. Load scenarios via load_scenarios(project_id)
  3. Create driver via create_driver(driver_mode, project_id)
  4. For each scenario:
     a. Run conversation (send_turn loop)
     b. Run evaluators via evaluate_scenario()
     c. Write EvalResult rows via create_batch
     d. Commit per-scenario for progress visibility
  5. Update counts + status → 'completed'
  On exception: status → 'failed', error_message stored
```

---

## Implementation Sequence

1. **Day 1**: `_llm.py` + `evaluators/tool_call.py` (E1) + `evaluators/groundedness.py` (E3) + `_evaluators.py` + unit tests
2. **Day 2**: `evaluators/menu_hallucination.py` (E2) + `evaluators/allergy_safety.py` (E4) + `_driver_factory.py` + `_runner.py` + unit tests
3. **Day 3**: Integration test + `mark_stale_runs_failed` + `get_scorecard` + exports + E5-E8 adapters (if available) + validation

---

## Test Strategy

| Test File | Covers |
|-----------|--------|
| `test_runner.py` | Status transitions, GC set, scorecard, stale run recovery |
| `test_evaluators.py` | Evaluator selection, results aggregation |
| `test_tool_call_evaluator.py` | E1: exact/partial/missing/unexpected calls |
| `test_groundedness_evaluator.py` | E3: deterministic + LLM fallback |
| `test_menu_hallucination_evaluator.py` | E2: hallucinated vs clean responses |
| `test_allergy_safety_evaluator.py` | E4: guarantee/deferral/fabrication |
| `test_driver_factory.py` | Driver construction, unknown mode error |

---

## Risks

1. **pal-agents evals availability**: Use `try/except ImportError` for E5-E8 and ConversationRunner
2. **HTTPDriver base_url**: Use env var `EVAL_API_BASE_URL` defaulting to `http://localhost:8000`
3. **LLM cost**: ~40 Haiku calls per 10-scenario run (~$0.02/run)
4. **Concurrent runs**: Consider 409 if run already pending/running for same project

---

## Validation

```bash
uv run pytest tests/services/eval_service/ -v
./scripts/validate.sh
```
