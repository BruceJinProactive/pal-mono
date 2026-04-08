"""Eval Repository Integration Tests.

Tests EvalRun, EvalResult, and AgentConfigSnapshot repository-layer
CRUD against real PostgreSQL to catch greenlet errors (lazy loading,
detached objects, attribute access after flush/refresh in async context).
"""

import uuid
from datetime import UTC, datetime
from typing import AsyncGenerator

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from db.repositories.agent_config_snapshot_repository import (
    AgentConfigSnapshotRepositoryAsync,
)
from db.repositories.eval_result_repository import EvalResultRepositoryAsync
from db.repositories.eval_run_repository import EvalRunRepositoryAsync
from db.settings import db_settings
from db.tables import AgentConfigSnapshot, EvalResult, EvalRun

# ---------------------------------------------------------------------------
# Function-scoped async engine + session to avoid event-loop mismatch.
# ---------------------------------------------------------------------------


@pytest.fixture
async def async_session() -> AsyncGenerator[AsyncSession, None]:
    """Function-scoped async SAVEPOINT session with its own engine."""
    engine = create_async_engine(
        db_settings.get_db_url_async(),
        pool_size=2,
        max_overflow=0,
        pool_pre_ping=True,
    )
    async with engine.connect() as conn:
        trans = await conn.begin()
        await conn.begin_nested()
        session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint")

        @event.listens_for(session.sync_session, "after_transaction_end")
        def restart_savepoint(session_inner, transaction):  # type: ignore[no-untyped-def]
            if conn.closed:
                return
            if not conn.in_nested_transaction():
                conn.sync_connection.begin_nested()  # type: ignore[union-attr]

        yield session
        await session.close()
        await trans.rollback()
    await engine.dispose()


# ---------------------------------------------------------------------------
# Helpers — create prerequisite rows inside the async session
# ---------------------------------------------------------------------------


def _make_eval_run(
    project_id: uuid.UUID,
    account_id: uuid.UUID,
    *,
    driver_mode: str = "http",
    status: str = "pending",
    triggered_by: str = "api",
) -> EvalRun:
    return EvalRun(
        id=uuid.uuid4(),
        project_id=project_id,
        account_id=account_id,
        driver_mode=driver_mode,
        status=status,
        triggered_by=triggered_by,
    )


def _make_eval_result(
    eval_run_id: uuid.UUID,
    *,
    scenario_id: str = "scenario-1",
    metric_name: str = "faithfulness",
    score: float = 0.85,
    passed: bool = True,
    reason: str = "Good",
) -> EvalResult:
    return EvalResult(
        id=uuid.uuid4(),
        eval_run_id=eval_run_id,
        scenario_id=scenario_id,
        metric_name=metric_name,
        score=score,
        passed=passed,
        reason=reason,
    )


# ---------------------------------------------------------------------------
# EvalRunRepositoryAsync Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestEvalRunRepository:
    """Async repository tests for EvalRunRepositoryAsync.

    Each test exercises flush + refresh + attribute access to surface
    greenlet errors that only appear with real async PostgreSQL sessions.
    """

    async def test_create_and_get_by_id(self, async_session: AsyncSession) -> None:
        """Create a run, read it back — attribute access after refresh is safe."""
        repo = EvalRunRepositoryAsync(async_session)
        project_id = uuid.uuid4()
        account_id = uuid.uuid4()

        run = _make_eval_run(project_id, account_id)
        created = await repo.create(run)

        # Attribute access after flush+refresh — greenlet risk zone
        assert created.id is not None
        assert created.project_id == project_id
        assert created.account_id == account_id
        assert created.status == "pending"
        assert created.driver_mode == "http"
        assert created.scenario_count == 0
        assert created.passed_count == 0
        assert created.failed_count == 0
        assert created.overall_score is None
        assert created.created_at is not None

        # Read back
        fetched = await repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.project_id == project_id

    async def test_get_by_id_returns_none_for_missing(
        self, async_session: AsyncSession
    ) -> None:
        """Non-existent ID returns None, not a greenlet error."""
        repo = EvalRunRepositoryAsync(async_session)
        result = await repo.get_by_id(uuid.uuid4())
        assert result is None

    async def test_update_status_lifecycle(self, async_session: AsyncSession) -> None:
        """pending -> running -> completed lifecycle with timestamp attributes."""
        repo = EvalRunRepositoryAsync(async_session)
        run = _make_eval_run(uuid.uuid4(), uuid.uuid4())
        created = await repo.create(run)

        # Mark running
        now = datetime.now(UTC)
        updated = await repo.update_status(created.id, "running", started_at=now)
        assert updated is not None
        assert updated.status == "running"
        assert updated.started_at is not None

        # Mark completed
        completed_at = datetime.now(UTC)
        updated2 = await repo.update_status(
            created.id, "completed", completed_at=completed_at
        )
        assert updated2 is not None
        assert updated2.status == "completed"
        assert updated2.completed_at is not None

    async def test_update_status_with_error_message(
        self, async_session: AsyncSession
    ) -> None:
        """Failed status with error_message — string attribute after refresh."""
        repo = EvalRunRepositoryAsync(async_session)
        run = _make_eval_run(uuid.uuid4(), uuid.uuid4())
        created = await repo.create(run)

        updated = await repo.update_status(
            created.id,
            "failed",
            completed_at=datetime.now(UTC),
            error_message="Something went wrong",
        )
        assert updated is not None
        assert updated.status == "failed"
        assert updated.error_message == "Something went wrong"

    async def test_update_status_nonexistent_returns_none(
        self, async_session: AsyncSession
    ) -> None:
        repo = EvalRunRepositoryAsync(async_session)
        result = await repo.update_status(uuid.uuid4(), "running")
        assert result is None

    async def test_update_counts(self, async_session: AsyncSession) -> None:
        """Update scenario counts and overall_score — numeric attributes after refresh."""
        repo = EvalRunRepositoryAsync(async_session)
        run = _make_eval_run(uuid.uuid4(), uuid.uuid4())
        created = await repo.create(run)

        updated = await repo.update_counts(
            created.id,
            scenario_count=10,
            passed_count=8,
            failed_count=2,
            overall_score=0.8,
        )
        assert updated is not None
        assert updated.scenario_count == 10
        assert updated.passed_count == 8
        assert updated.failed_count == 2
        assert updated.overall_score == pytest.approx(0.8)

    async def test_update_counts_nonexistent_returns_none(
        self, async_session: AsyncSession
    ) -> None:
        repo = EvalRunRepositoryAsync(async_session)
        result = await repo.update_counts(uuid.uuid4(), scenario_count=5)
        assert result is None

    async def test_get_by_project_ordering(self, async_session: AsyncSession) -> None:
        """Multiple runs for same project returned in created_at DESC order."""
        repo = EvalRunRepositoryAsync(async_session)
        project_id = uuid.uuid4()
        account_id = uuid.uuid4()

        ids = []
        for _ in range(3):
            run = _make_eval_run(project_id, account_id)
            created = await repo.create(run)
            ids.append(created.id)

        runs = await repo.get_by_project(project_id)
        assert len(runs) == 3
        # Most recent first — each has attribute access
        for r in runs:
            assert r.project_id == project_id
            assert r.created_at is not None

    async def test_get_by_project_status_filter(
        self, async_session: AsyncSession
    ) -> None:
        """Filter by status works correctly."""
        repo = EvalRunRepositoryAsync(async_session)
        project_id = uuid.uuid4()
        account_id = uuid.uuid4()

        pending_run = _make_eval_run(project_id, account_id, status="pending")
        await repo.create(pending_run)

        completed_run = _make_eval_run(project_id, account_id, status="completed")
        await repo.create(completed_run)

        pending_runs = await repo.get_by_project(project_id, status="pending")
        assert len(pending_runs) == 1
        assert pending_runs[0].status == "pending"

        completed_runs = await repo.get_by_project(project_id, status="completed")
        assert len(completed_runs) == 1
        assert completed_runs[0].status == "completed"

    async def test_get_by_project_empty(self, async_session: AsyncSession) -> None:
        """Non-existent project returns empty list, not error."""
        repo = EvalRunRepositoryAsync(async_session)
        runs = await repo.get_by_project(uuid.uuid4())
        assert runs == []

    async def test_full_lifecycle_attribute_access(
        self, async_session: AsyncSession
    ) -> None:
        """Full create -> update_status -> update_counts -> get_by_id lifecycle.

        This is the most important greenlet test: it exercises multiple
        flush/refresh cycles on the same object, then re-fetches and accesses
        every attribute — exactly what _run_eval_background does.
        """
        repo = EvalRunRepositoryAsync(async_session)
        project_id = uuid.uuid4()
        account_id = uuid.uuid4()

        # Create
        run = _make_eval_run(project_id, account_id)
        created = await repo.create(run)
        run_id = created.id

        # Mark running
        await repo.update_status(run_id, "running", started_at=datetime.now(UTC))

        # Update counts
        await repo.update_counts(
            run_id,
            scenario_count=5,
            passed_count=4,
            failed_count=1,
            overall_score=0.8,
        )

        # Mark completed
        await repo.update_status(run_id, "completed", completed_at=datetime.now(UTC))

        # Fresh fetch — access every attribute
        final = await repo.get_by_id(run_id)
        assert final is not None
        assert final.id == run_id
        assert final.project_id == project_id
        assert final.account_id == account_id
        assert final.status == "completed"
        assert final.scenario_count == 5
        assert final.passed_count == 4
        assert final.failed_count == 1
        assert final.overall_score == pytest.approx(0.8)
        assert final.started_at is not None
        assert final.completed_at is not None
        assert final.error_message is None
        assert final.created_at is not None

    async def test_update_generic(self, async_session: AsyncSession) -> None:
        """Generic update() with kwargs — exercises setattr + flush + refresh."""
        repo = EvalRunRepositoryAsync(async_session)
        run = _make_eval_run(uuid.uuid4(), uuid.uuid4())
        created = await repo.create(run)

        updated = await repo.update(created.id, status="running", driver_mode="direct")
        assert updated is not None
        assert updated.status == "running"
        assert updated.driver_mode == "direct"


# ---------------------------------------------------------------------------
# EvalResultRepositoryAsync Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestEvalResultRepository:
    """Async repository tests for EvalResultRepositoryAsync.

    Exercises attribute access on EvalResult after flush/refresh
    to catch greenlet errors with JSONB and nullable fields.
    """

    async def test_create_and_access_attributes(
        self, async_session: AsyncSession
    ) -> None:
        """Create a result, access all attributes — greenlet risk on JSONB."""
        # First create an eval run (parent)
        run_repo = EvalRunRepositoryAsync(async_session)
        run = _make_eval_run(uuid.uuid4(), uuid.uuid4())
        created_run = await run_repo.create(run)

        repo = EvalResultRepositoryAsync(async_session)
        result = EvalResult(
            id=uuid.uuid4(),
            eval_run_id=created_run.id,
            scenario_id="scenario-greet",
            metric_name="faithfulness",
            score=0.92,
            passed=True,
            reason="All claims verified",
            raw_output={"claims": ["a", "b"], "verdicts": [True, True]},
        )
        created = await repo.create(result)

        # Attribute access after refresh — especially raw_output (JSONB)
        assert created.id is not None
        assert created.eval_run_id == created_run.id
        assert created.scenario_id == "scenario-greet"
        assert created.metric_name == "faithfulness"
        assert created.score == pytest.approx(0.92)
        assert created.passed is True
        assert created.reason == "All claims verified"
        assert created.raw_output == {"claims": ["a", "b"], "verdicts": [True, True]}
        assert created.evaluated_at is not None

    async def test_create_with_nullable_fields(
        self, async_session: AsyncSession
    ) -> None:
        """Result with None reason and raw_output — nullable access after refresh."""
        run_repo = EvalRunRepositoryAsync(async_session)
        run = _make_eval_run(uuid.uuid4(), uuid.uuid4())
        created_run = await run_repo.create(run)

        repo = EvalResultRepositoryAsync(async_session)
        result = EvalResult(
            id=uuid.uuid4(),
            eval_run_id=created_run.id,
            scenario_id="scenario-null",
            metric_name="responsive",
            score=0.5,
            passed=False,
            reason=None,
            raw_output=None,
        )
        created = await repo.create(result)
        assert created.reason is None
        assert created.raw_output is None

    async def test_create_batch_and_refresh(self, async_session: AsyncSession) -> None:
        """Batch create + per-item refresh — greenlet risk on loop of refreshes."""
        run_repo = EvalRunRepositoryAsync(async_session)
        run = _make_eval_run(uuid.uuid4(), uuid.uuid4())
        created_run = await run_repo.create(run)

        repo = EvalResultRepositoryAsync(async_session)
        results = [
            _make_eval_result(
                created_run.id,
                scenario_id=f"scenario-{i}",
                metric_name=f"metric-{i}",
                score=0.1 * i,
                passed=i > 5,
            )
            for i in range(1, 8)
        ]

        created = await repo.create_batch(results)
        assert len(created) == 7

        # Access attributes on each — multiple refreshed objects
        for i, r in enumerate(created, start=1):
            assert r.scenario_id == f"scenario-{i}"
            assert r.metric_name == f"metric-{i}"
            assert r.score == pytest.approx(0.1 * i)
            assert r.evaluated_at is not None

    async def test_create_batch_empty(self, async_session: AsyncSession) -> None:
        """Empty batch returns empty list."""
        repo = EvalResultRepositoryAsync(async_session)
        result = await repo.create_batch([])
        assert result == []

    async def test_get_by_run_id(self, async_session: AsyncSession) -> None:
        """Retrieve results by run ID — list iteration with attribute access."""
        run_repo = EvalRunRepositoryAsync(async_session)
        run = _make_eval_run(uuid.uuid4(), uuid.uuid4())
        created_run = await run_repo.create(run)

        repo = EvalResultRepositoryAsync(async_session)
        for metric in ["faithfulness", "responsive", "voice_appropriate"]:
            result = _make_eval_result(created_run.id, metric_name=metric, score=0.9)
            await repo.create(result)

        fetched = await repo.get_by_run_id(created_run.id)
        assert len(fetched) == 3
        metric_names = {r.metric_name for r in fetched}
        assert metric_names == {"faithfulness", "responsive", "voice_appropriate"}

    async def test_get_by_run_id_empty(self, async_session: AsyncSession) -> None:
        """Non-existent run returns empty list."""
        repo = EvalResultRepositoryAsync(async_session)
        results = await repo.get_by_run_id(uuid.uuid4())
        assert results == []

    async def test_get_by_scenario(self, async_session: AsyncSession) -> None:
        """Retrieve results by scenario within a run — cross-attribute access."""
        run_repo = EvalRunRepositoryAsync(async_session)
        run = _make_eval_run(uuid.uuid4(), uuid.uuid4())
        created_run = await run_repo.create(run)

        repo = EvalResultRepositoryAsync(async_session)
        # Two metrics for scenario-A, one for scenario-B
        await repo.create(
            _make_eval_result(created_run.id, scenario_id="scenario-A", metric_name="f")
        )
        await repo.create(
            _make_eval_result(created_run.id, scenario_id="scenario-A", metric_name="r")
        )
        await repo.create(
            _make_eval_result(created_run.id, scenario_id="scenario-B", metric_name="f")
        )

        scenario_a = await repo.get_by_scenario(created_run.id, "scenario-A")
        assert len(scenario_a) == 2
        assert all(r.scenario_id == "scenario-A" for r in scenario_a)

        scenario_b = await repo.get_by_scenario(created_run.id, "scenario-B")
        assert len(scenario_b) == 1

    async def test_run_with_multiple_scenarios_full_lifecycle(
        self, async_session: AsyncSession
    ) -> None:
        """Simulates what _run_eval_background does: create run, add results
        per scenario, then fetch all — the critical greenlet path."""
        run_repo = EvalRunRepositoryAsync(async_session)
        result_repo = EvalResultRepositoryAsync(async_session)

        project_id = uuid.uuid4()
        run = _make_eval_run(project_id, uuid.uuid4())
        created_run = await run_repo.create(run)
        await run_repo.update_status(
            created_run.id, "running", started_at=datetime.now(UTC)
        )

        # Simulate per-scenario result writes (as _run_eval_background does)
        scenarios = ["greet", "order", "cancel"]
        metrics = ["faithfulness", "responsive", "task_completion"]
        for scenario in scenarios:
            for metric in metrics:
                r = EvalResult(
                    id=uuid.uuid4(),
                    eval_run_id=created_run.id,
                    scenario_id=scenario,
                    metric_name=metric,
                    score=0.85,
                    passed=True,
                    reason=f"{metric} passed for {scenario}",
                )
                await result_repo.create(r)
            # Flush per-scenario like the runner does
            await async_session.flush()

        # Update final counts
        await run_repo.update_counts(
            created_run.id,
            scenario_count=3,
            passed_count=3,
            failed_count=0,
            overall_score=1.0,
        )
        await run_repo.update_status(
            created_run.id, "completed", completed_at=datetime.now(UTC)
        )

        # Fetch everything back — attribute access on every field
        final_run = await run_repo.get_by_id(created_run.id)
        assert final_run is not None
        assert final_run.status == "completed"
        assert final_run.scenario_count == 3
        assert final_run.overall_score == pytest.approx(1.0)

        all_results = await result_repo.get_by_run_id(created_run.id)
        assert len(all_results) == 9  # 3 scenarios * 3 metrics
        for r in all_results:
            assert r.score == pytest.approx(0.85)
            assert r.passed is True
            assert r.reason is not None
            assert r.evaluated_at is not None


# ---------------------------------------------------------------------------
# AgentConfigSnapshotRepositoryAsync Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAgentConfigSnapshotRepository:
    """Async repository tests for AgentConfigSnapshotRepositoryAsync.

    The get_or_create upsert uses pg_insert + RETURNING + xmax, which is
    particularly susceptible to greenlet issues with the raw result tuple.
    """

    async def test_get_or_create_insert(self, async_session: AsyncSession) -> None:
        """First insert returns created=True with all attributes accessible."""
        repo = AgentConfigSnapshotRepositoryAsync(async_session)
        agent_id = uuid.uuid4()
        project_id = uuid.uuid4()
        fingerprint = uuid.uuid4().hex

        snapshot = AgentConfigSnapshot(
            fingerprint=fingerprint,
            agent_id=agent_id,
            project_id=project_id,
            system_prompt_hash="abc123",
            system_prompt_text="You are a helpful assistant.",
            config_snapshot={"model": "gpt-4", "temperature": 0.7},
        )

        row, created = await repo.get_or_create(snapshot)
        assert created is True
        assert row.fingerprint == fingerprint
        assert row.agent_id == agent_id
        assert row.project_id == project_id
        assert row.system_prompt_hash == "abc123"
        assert row.system_prompt_text == "You are a helpful assistant."
        assert row.config_snapshot == {"model": "gpt-4", "temperature": 0.7}
        assert row.first_seen_at is not None
        assert row.last_seen_at is not None

    async def test_get_or_create_upsert(self, async_session: AsyncSession) -> None:
        """Second call with same fingerprint returns created=False and updates last_seen_at."""
        repo = AgentConfigSnapshotRepositoryAsync(async_session)
        fingerprint = uuid.uuid4().hex
        agent_id = uuid.uuid4()
        project_id = uuid.uuid4()

        snapshot1 = AgentConfigSnapshot(
            fingerprint=fingerprint,
            agent_id=agent_id,
            project_id=project_id,
            system_prompt_hash="hash1",
            system_prompt_text="Prompt v1",
            config_snapshot={"version": 1},
        )
        row1, created1 = await repo.get_or_create(snapshot1)
        assert created1 is True
        first_last_seen = row1.last_seen_at

        # Upsert same fingerprint
        snapshot2 = AgentConfigSnapshot(
            fingerprint=fingerprint,
            agent_id=agent_id,
            project_id=project_id,
            system_prompt_hash="hash1",
            system_prompt_text="Prompt v1",
            config_snapshot={"version": 1},
        )
        row2, created2 = await repo.get_or_create(snapshot2)
        assert created2 is False
        assert row2.fingerprint == fingerprint
        # last_seen_at should be updated (>= first)
        assert row2.last_seen_at >= first_last_seen

    async def test_get_by_fingerprint(self, async_session: AsyncSession) -> None:
        """Retrieve by fingerprint — JSONB attribute access after scalar_one_or_none."""
        repo = AgentConfigSnapshotRepositoryAsync(async_session)
        fingerprint = uuid.uuid4().hex

        snapshot = AgentConfigSnapshot(
            fingerprint=fingerprint,
            agent_id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            system_prompt_hash="xyz",
            system_prompt_text="Test prompt",
            config_snapshot={"key": "value"},
        )
        await repo.get_or_create(snapshot)

        fetched = await repo.get_by_fingerprint(fingerprint)
        assert fetched is not None
        assert fetched.config_snapshot == {"key": "value"}
        assert fetched.system_prompt_text == "Test prompt"

    async def test_get_by_fingerprint_missing(
        self, async_session: AsyncSession
    ) -> None:
        """Non-existent fingerprint returns None."""
        repo = AgentConfigSnapshotRepositoryAsync(async_session)
        result = await repo.get_by_fingerprint("nonexistent")
        assert result is None

    async def test_get_by_agent_id(self, async_session: AsyncSession) -> None:
        """Multiple snapshots for same agent — list access with attributes."""
        repo = AgentConfigSnapshotRepositoryAsync(async_session)
        agent_id = uuid.uuid4()
        project_id = uuid.uuid4()

        for i in range(3):
            snapshot = AgentConfigSnapshot(
                fingerprint=uuid.uuid4().hex,
                agent_id=agent_id,
                project_id=project_id,
                system_prompt_hash=f"hash-{i}",
                system_prompt_text=f"Prompt version {i}",
                config_snapshot={"version": i},
            )
            await repo.get_or_create(snapshot)

        snapshots = await repo.get_by_agent_id(agent_id)
        assert len(snapshots) == 3
        for s in snapshots:
            assert s.agent_id == agent_id
            assert s.config_snapshot is not None
            assert s.first_seen_at is not None

    async def test_get_by_agent_id_empty(self, async_session: AsyncSession) -> None:
        """Non-existent agent returns empty list."""
        repo = AgentConfigSnapshotRepositoryAsync(async_session)
        result = await repo.get_by_agent_id(uuid.uuid4())
        assert result == []


# ---------------------------------------------------------------------------
# Service-level integration: create_eval_run + model_validate after commit
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCreateEvalRunCommitRefresh:
    """Regression test for greenlet error when accessing ORM attributes
    after session.commit() in create_eval_run.

    session.commit() expires all ORM attributes. Without an explicit
    refresh, model_validate(run) triggers a lazy load that fails in async
    context with 'greenlet_spawn has not been called'.
    """

    async def test_create_eval_run_returns_accessible_attributes(
        self, async_session: AsyncSession
    ) -> None:
        """Call the actual create_eval_run service function and access attributes.

        This is the exact code path the route handler uses:
        create_eval_run() -> EvalRunResponse.model_validate(run).
        Before the fix, this raised MissingGreenlet.
        """
        from unittest.mock import patch

        from api.schemas.eval.responses import EvalRunResponse
        from services.eval_service._runner import create_eval_run

        project_id = uuid.uuid4()
        account_id = uuid.uuid4()

        # Patch out background task scheduling — we only test the DB path
        with patch("services.eval_service._runner._schedule_eval_background"):
            run = await create_eval_run(
                project_id=project_id,
                account_id=account_id,
                driver_mode="http",
                triggered_by="api",
                session=async_session,
            )

        # This is what the route handler does — if refresh is missing, this explodes
        response = EvalRunResponse.model_validate(run)
        assert response.id == run.id
        assert response.project_id == project_id
        assert response.status == "pending"
        assert response.driver_mode == "http"
        assert response.triggered_by == "api"
        assert response.scenario_count == 0
        assert response.created_at is not None

    async def test_attributes_fail_without_refresh_after_commit(
        self, async_session: AsyncSession
    ) -> None:
        """Proves the bug: without refresh after commit, attribute access raises."""
        from sqlalchemy.exc import MissingGreenlet

        repo = EvalRunRepositoryAsync(async_session)
        run = _make_eval_run(uuid.uuid4(), uuid.uuid4())
        run = await repo.create(run)
        await async_session.commit()
        # Deliberately skip refresh — this is what the old code did

        with pytest.raises(MissingGreenlet):
            _ = run.status

    async def test_upsert_then_fetch_lifecycle(
        self, async_session: AsyncSession
    ) -> None:
        """Full lifecycle: insert -> upsert -> fetch by fingerprint -> fetch by agent.

        This exercises multiple flush/refresh/execute cycles on the same session
        to maximally stress the async greenlet boundary.
        """
        repo = AgentConfigSnapshotRepositoryAsync(async_session)
        agent_id = uuid.uuid4()
        project_id = uuid.uuid4()
        fingerprint = uuid.uuid4().hex

        # Insert
        snapshot = AgentConfigSnapshot(
            fingerprint=fingerprint,
            agent_id=agent_id,
            project_id=project_id,
            system_prompt_hash="initial",
            system_prompt_text="Hello world",
            config_snapshot={"tools": ["search", "lookup"]},
        )
        row, created = await repo.get_or_create(snapshot)
        assert created is True

        # Upsert (touch last_seen_at)
        snapshot2 = AgentConfigSnapshot(
            fingerprint=fingerprint,
            agent_id=agent_id,
            project_id=project_id,
            system_prompt_hash="initial",
            system_prompt_text="Hello world",
            config_snapshot={"tools": ["search", "lookup"]},
        )
        row2, created2 = await repo.get_or_create(snapshot2)
        assert created2 is False

        # Fetch by fingerprint
        by_fp = await repo.get_by_fingerprint(fingerprint)
        assert by_fp is not None
        assert by_fp.config_snapshot["tools"] == ["search", "lookup"]

        # Fetch by agent
        by_agent = await repo.get_by_agent_id(agent_id)
        assert len(by_agent) == 1
        assert by_agent[0].fingerprint == fingerprint
        assert by_agent[0].system_prompt_text == "Hello world"
