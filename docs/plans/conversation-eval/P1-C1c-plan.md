# P1-C1c: Implement EvalResultRepository

**Task:** https://www.notion.so/3318c0822e498101ba33c97573a6a08c
**Type:** CODE
**Est. Hours:** 2
**Blocked by:** P1-C1a (EvalResult table migration), P1-C1b (EvalRunRepository, because results are only created after a run exists)

---

## Background

`EvalResult` records a single metric verdict for one scenario within an eval run. Each row captures `metric_name`, `score`, `passed`, optional `reason`, and an optional `raw_output` JSONB blob. A single scenario typically produces several rows (one per metric), so batch insertion is the normal write path.

Results are append-only — no update or delete methods are needed.

---

## Implementation Steps

- [ ] **Step 1: Create `db/repositories/eval_result_repository.py`**

  ```python
  from __future__ import annotations

  import uuid

  from sqlalchemy import select
  from sqlalchemy.exc import SQLAlchemyError
  from sqlalchemy.ext.asyncio import AsyncSession

  from db.tables import EvalResult
  from utils.log import logger


  class EvalResultRepositoryAsync:
      """Async repository for eval result operations."""

      def __init__(self, session: AsyncSession) -> None:
          self.session = session
  ```

  Implement these methods:

  - `create(result: EvalResult) -> EvalResult`
    - `session.add(result)` → `flush()` → `refresh(result)` → return
    - Raise `SQLAlchemyError` on failure

  - `create_batch(results: list[EvalResult]) -> list[EvalResult]`
    - `session.add_all(results)` → `flush()`
    - Refresh each result individually with `await session.refresh(r)` (SQLAlchemy async does not support bulk refresh)
    - Return the refreshed list
    - Raise `SQLAlchemyError` on failure; roll back before re-raising

  - `get_by_run_id(eval_run_id: uuid.UUID) -> list[EvalResult]`
    - `select(EvalResult).filter(EvalResult.eval_run_id == eval_run_id)`
    - Order by `evaluated_at ASC` for stable iteration
    - Return `[]` on `SQLAlchemyError`

  - `get_by_scenario(eval_run_id: uuid.UUID, scenario_id: str) -> list[EvalResult]`
    - Filter on both `eval_run_id` and `scenario_id`
    - Returns all metric rows for that scenario within the run
    - Return `[]` on `SQLAlchemyError`

- [ ] **Step 2: Export from `db/repositories/__init__.py`**

  Add `EvalResultRepositoryAsync` to the module's public exports.

- [ ] **Step 3: Write tests in `tests/db/repositories/test_eval_result_repository.py`**

  Use `AsyncMock` / `MagicMock` for the session; pin all `MagicMock` optional fields explicitly (see project CLAUDE.md).

  Test cases:
  - `create` — happy path returns the result; `SQLAlchemyError` propagates and calls `rollback()`
  - `create_batch` — empty list returns `[]` without touching the session; non-empty list calls `add_all` and refreshes each row; `SQLAlchemyError` rolls back and re-raises
  - `get_by_run_id` — returns all results for a run; empty list when none found; `[]` on `SQLAlchemyError`
  - `get_by_scenario` — filters by both `eval_run_id` and `scenario_id`; returns `[]` when no match; `[]` on `SQLAlchemyError`

---

## Validation

```bash
uv run pytest tests/db/repositories/test_eval_result_repository.py -v
./scripts/validate.sh
```

---

## Risks & Open Questions

- `create_batch` refreshes rows one-by-one in a loop. For very large batches (hundreds of results) this could be slow; if profiling shows it is a bottleneck, switch to a bulk `INSERT … RETURNING` via `session.execute(insert(EvalResult).returning(EvalResult), [row_dicts])`. Keep the simple loop for now.
- `scenario_id` is `String(255)` — confirm at implementation time that the eval runner uses a stable, globally unique identifier for scenarios (e.g. slug or UUID string) so that `get_by_scenario` returns meaningful results across multiple runs.
