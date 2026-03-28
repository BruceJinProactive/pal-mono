# P1-C1a: EvalRun + EvalResult + AgentConfigSnapshot models + migration

**Task:** https://www.notion.so/3318c0822e498121a892c025be2adc2e
**Type:** CODE
**Est. Hours:** 3
**Blocked by:** None

---

## Background

Three new tables for the eval platform. Follow existing patterns from `db/tables/agents.py`: inherit from `Base`, use `Mapped[]` typed columns, UUID PKs, `DateTime(timezone=True)` timestamps, JSONB for flexible data.

CRITICAL: Export all 3 models in `db/tables/__init__.py` BEFORE running `alembic autogenerate`.

---

## Implementation Steps

- [x] **Step 1: Create `db/tables/eval_runs.py`**

  EvalRun model with id, project_id, account_id, agent_fingerprint, driver_mode,
  status (pending/running/completed/failed), triggered_by (api/scheduler/ci),
  scenario_count, passed_count, failed_count, overall_score, started_at,
  completed_at, error_message, created_at, updated_at.

- [x] **Step 2: Create `db/tables/eval_results.py`**

  EvalResult model with id, eval_run_id (FK), scenario_id, conversation_id,
  agent_fingerprint, metric_name, score, passed, reason, raw_output (JSONB),
  evaluated_at.

- [x] **Step 3: Create `db/tables/agent_config_snapshots.py`**

  AgentConfigSnapshot model with fingerprint (String(64) PK), agent_id,
  project_id, system_prompt_hash, system_prompt_text, config_snapshot (JSONB),
  first_seen_at, last_seen_at.

- [x] **Step 4: Export in `db/tables/__init__.py`**

  Added imports for all 3 models.

- [ ] **Step 5: Generate and verify migration**

  ```bash
  docker exec -it pal-mono-api alembic -c db/alembic.ini revision --autogenerate -m "add-eval-tables"
  docker exec -it pal-mono-api alembic -c db/alembic.ini upgrade head
  docker exec -it pal-mono-api alembic -c db/alembic.ini downgrade -1
  docker exec -it pal-mono-api alembic -c db/alembic.ini upgrade head
  ```

---

## Validation

```bash
./scripts/validate.sh
# Verify tables in psql:
docker exec -it pal-mono-db psql -U postgres -d palona -c "\dt eval_*"
docker exec -it pal-mono-db psql -U postgres -d palona -c "\dt agent_config_snapshots"
```

---

## Risks & Open Questions

- If Docker is not running, migration generation must wait — models can still be written and validated with pyright
- Check if `EvalRunStatus`/`EvalRunTriggeredBy` should be SQLAlchemy Enum types or plain strings — existing codebase uses both patterns. Prefer String columns with Python enums for flexibility.
