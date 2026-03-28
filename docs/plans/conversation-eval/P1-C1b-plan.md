# P1-C1b: Implement EvalRunRepository

**Task:** https://www.notion.so/3318c0822e4981158a2ac30dad1cc40c
**Type:** CODE
**Est. Hours:** 3
**Blocked by:** P1-C1a (EvalRun table must be migrated before the repository can be exercised)

---

## Background

`EvalRun` tracks the lifecycle of a single evaluation execution: status (`pending` → `running` → `completed` / `failed`), per-run counters (`scenario_count`, `passed_count`, `failed_count`), and an optional `overall_score`. The repository is the sole access point for all eval-run persistence — services must never issue raw ORM queries against `eval_runs`.

The pattern follows `MonitoringRunRepositoryAsync` in `db/repositories/monitoring_run_repository.py` exactly: async-only, `AsyncSession` injected via constructor, `flush()`+`refresh()` instead of `commit()` (callers own the transaction), and `SQLAlchemyError` catch-with-rollback on every method.

---

## Implementation Steps

- [ ] **Step 1: Create `db/repositories/eval_run_repository.py`**

  ```python
  from __future__ import annotations

  import uuid
  from datetime import datetime

  from sqlalchemy import select
  from sqlalchemy.exc import SQLAlchemyError
  from sqlalchemy.ext.asyncio import AsyncSession

  from db.tables import EvalRun
  from utils.log import logger


  class EvalRunRepositoryAsync:
      """Async repository for eval run operations."""

      def __init__(self, session: AsyncSession) -> None:
          self.session = session
  ```

  Implement these methods (all `async`, full docstrings, type-annotated):

  - `create(run: EvalRun) -> EvalRun`
    - `session.add(run)` → `flush()` → `refresh(run)` → return
    - Raise `SQLAlchemyError` on failure (same as `MonitoringRunRepositoryAsync.create`)

  - `get_by_id(run_id: uuid.UUID) -> EvalRun | None`
    - `select(EvalRun).filter(EvalRun.id == run_id)`
    - Return `None` on `SQLAlchemyError`

  - `get_by_project(project_id: uuid.UUID, *, status: str | None = None, start_date: datetime | None = None, end_date: datetime | None = None) -> list[EvalRun]`
    - Filter by `project_id`; optionally narrow by `status`, `started_at >= start_date`, `started_at <= end_date`
    - Order by `created_at DESC` (most-recent run first)
    - Return `[]` on `SQLAlchemyError`

  - `update_status(run_id: uuid.UUID, status: str, *, started_at: datetime | None = None, completed_at: datetime | None = None, error_message: str | None = None) -> EvalRun | None`
    - Fetch via `get_by_id`; return `None` if not found
    - Set `status`; set `started_at` / `completed_at` / `error_message` only when the caller provides a non-`None` value
    - `flush()` → `refresh()` → return

  - `update_counts(run_id: uuid.UUID, *, scenario_count: int | None = None, passed_count: int | None = None, failed_count: int | None = None, overall_score: float | None = None) -> EvalRun | None`
    - Same fetch-then-setattr pattern as `update_status`
    - Only overwrite fields that are explicitly passed (not `None`)

- [ ] **Step 2: Export from `db/repositories/__init__.py`**

  Add `EvalRunRepositoryAsync` to the module's public exports, following the pattern used for `MonitoringRunRepositoryAsync`.

- [ ] **Step 3: Write tests in `tests/db/repositories/test_eval_run_repository.py`**

  Use `AsyncMock` / `MagicMock` for the session; do not require a live database.

  Test cases:
  - `create` — happy path returns the run; `SQLAlchemyError` propagates and calls `rollback()`
  - `get_by_id` — found returns the run; not-found returns `None`; `SQLAlchemyError` returns `None`
  - `get_by_project` — no filters returns all runs ordered by `created_at DESC`; `status` filter narrows results; date filters applied; empty list on `SQLAlchemyError`
  - `update_status` — status and timestamps updated; run not found returns `None`; partial kwargs (only `started_at` provided) leaves other fields unchanged
  - `update_counts` — counts and score updated; run not found returns `None`; `None` kwargs leave fields unchanged

---

## Validation

```bash
uv run pytest tests/db/repositories/test_eval_run_repository.py -v
./scripts/validate.sh
```

---

## Risks & Open Questions

- `update_counts` is called concurrently by scenario workers during a run — callers should use `SELECT … FOR UPDATE` or serialise updates at the service layer to avoid lost writes. Document this constraint in the method docstring; do not implement locking here.
- `get_by_project` does not paginate. If a project accumulates thousands of runs, add `limit` / `offset` parameters at that time; leave them out of the initial implementation to keep the surface small.
