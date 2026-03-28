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

- [ ] **Step 1: Create `db/tables/eval_runs.py`**

  ```python
  from __future__ import annotations
  import uuid
  from datetime import datetime
  from sqlalchemy import DateTime, Enum, Float, Integer, String, Text, text
  from sqlalchemy.dialects.postgresql import UUID
  from sqlalchemy.orm import Mapped, mapped_column
  from .base import Base

  class EvalRunStatus(str, enum.Enum):
      PENDING = "pending"
      RUNNING = "running"
      COMPLETED = "completed"
      FAILED = "failed"

  class EvalRunTriggeredBy(str, enum.Enum):
      API = "api"
      SCHEDULER = "scheduler"
      CI = "ci"

  class EvalRun(Base):
      __tablename__ = "eval_runs"
      id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
      project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
      account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
      agent_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
      driver_mode: Mapped[str] = mapped_column(String(20), nullable=False)  # "http" | "direct" | "voice"
      status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
      triggered_by: Mapped[str] = mapped_column(String(20), nullable=False, default="api")
      scenario_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
      passed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
      failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
      overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)
      started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
      completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
      error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
      created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
      updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), onupdate=func.now())
  ```

- [ ] **Step 2: Create `db/tables/eval_results.py`**

  ```python
  class EvalResult(Base):
      __tablename__ = "eval_results"
      id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
      eval_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("eval_runs.id"), index=True)
      scenario_id: Mapped[str] = mapped_column(String(255), nullable=False)
      conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
      agent_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
      metric_name: Mapped[str] = mapped_column(String(100), nullable=False)
      score: Mapped[float] = mapped_column(Float, nullable=False)
      passed: Mapped[bool] = mapped_column(nullable=False)
      reason: Mapped[str | None] = mapped_column(Text, nullable=True)
      raw_output: Mapped[dict | None] = mapped_column(MutableDict.as_mutable(JSONB()), nullable=True)
      evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
  ```

- [ ] **Step 3: Create `db/tables/agent_config_snapshots.py`**

  ```python
  class AgentConfigSnapshot(Base):
      __tablename__ = "agent_config_snapshots"
      fingerprint: Mapped[str] = mapped_column(String(64), primary_key=True)
      agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
      project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
      system_prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
      system_prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
      config_snapshot: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSONB()), nullable=False)
      first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
      last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
  ```

- [ ] **Step 4: Export in `db/tables/__init__.py`**

  Add imports for all 3 models + enums:
  ```python
  from .eval_runs import EvalRun, EvalRunStatus, EvalRunTriggeredBy
  from .eval_results import EvalResult
  from .agent_config_snapshots import AgentConfigSnapshot
  ```

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
