"""Monitoring Integration Tests.

Tests monitoring config, monitoring run, signal source, and signal feed
DB operations and repository-layer CRUD against real PostgreSQL.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import AsyncGenerator

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Session

from db.repositories.monitoring_config_repository import MonitoringConfigRepositoryAsync
from db.repositories.monitoring_run_repository import MonitoringRunRepositoryAsync
from db.settings import db_settings
from db.tables import MonitoringConfig, MonitoringRun, SignalFeed, SignalSource
from db.tables.accounts import AccountStatus
from db.tables.types import SignalSourceStatus, SignalType
from tests.factories import (
    make_monitoring_config,
    make_monitoring_run,
    make_signal_feed,
    make_signal_source,
    make_world,
)

# ---------------------------------------------------------------------------
# Function-scoped async engine + session to avoid event-loop mismatch.
# The session-scoped async_engine in conftest binds connections to the first
# test's event loop, breaking subsequent tests. Override here.
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
# Async helpers — create test data within async_session so it's visible
# to async repository queries (sync db_session is a separate transaction).
# ---------------------------------------------------------------------------


async def _async_make_world(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    """Create Account + Agent + Project in async session. Returns (account_id, project_id)."""
    from db.tables import Account, Agent, Project

    now = datetime.now(UTC)
    account_id = uuid.uuid4()
    account = Account(
        id=account_id,
        name=f"test-account-{account_id.hex[:8]}",
        display_name="Test Account",
        status=AccountStatus.active,
        created_at=now,
        updated_at=now,
    )
    session.add(account)
    await session.flush()

    agent_id = uuid.uuid4()
    agent = Agent(
        id=agent_id,
        account_id=account_id,
        name=f"test-agent-{agent_id.hex[:8]}",
        created_at=now,
        updated_at=now,
    )
    session.add(agent)
    await session.flush()

    project_id = uuid.uuid4()
    project = Project(
        id=project_id,
        account_id=account_id,
        agent_id=agent_id,
        name=f"test-project-{project_id.hex[:8]}",
        created_at=now,
        updated_at=now,
    )
    session.add(project)
    await session.flush()

    return account_id, project_id


async def _async_make_signal_source(
    session: AsyncSession,
    account_id: uuid.UUID,
    project_id: uuid.UUID | None = None,
) -> SignalSource:
    """Create a SignalSource within async session."""
    now = datetime.now(UTC)
    ss_id = uuid.uuid4()
    ss = SignalSource(
        id=ss_id,
        account_id=account_id,
        project_id=project_id,
        signal_type=SignalType.camera,
        name=f"test-camera-{ss_id.hex[:8]}",
        status=SignalSourceStatus.active,
        config={},
        created_at=now,
        updated_at=now,
    )
    session.add(ss)
    await session.flush()
    return ss


async def _async_make_monitoring_config(
    session: AsyncSession,
    project_id: uuid.UUID,
    signal_source_id: uuid.UUID,
    name: str | None = None,
    enabled: bool = True,
) -> MonitoringConfig:
    """Create a MonitoringConfig within async session."""
    now = datetime.now(UTC)
    mc_id = uuid.uuid4()
    mc = MonitoringConfig(
        id=mc_id,
        project_id=project_id,
        signal_source_id=signal_source_id,
        name=name or f"test-monitor-{mc_id.hex[:8]}",
        rules={"prompt": "Check for cleanliness"},
        enabled=enabled,
        created_at=now,
        updated_at=now,
    )
    session.add(mc)
    await session.flush()
    return mc


async def _async_make_monitoring_run(
    session: AsyncSession,
    monitoring_config_id: uuid.UUID,
    started_at: datetime | None = None,
    evaluation_result: dict | None = None,  # type: ignore[type-arg]
    trigger_metadata: dict | None = None,  # type: ignore[type-arg]
) -> MonitoringRun:
    """Create a MonitoringRun within async session."""
    now = datetime.now(UTC)
    mr = MonitoringRun(
        id=uuid.uuid4(),
        monitoring_config_id=monitoring_config_id,
        trigger_metadata=trigger_metadata or {"source": "test"},
        started_at=started_at or now,
        evaluation_result=evaluation_result or {"result": "pass"},
    )
    session.add(mr)
    await session.flush()
    return mr


# ---------------------------------------------------------------------------
# Data Model Tests (sync db_session)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestMonitoringDataModel:
    """DB-layer tests for monitoring entities."""

    def test_monitoring_config_creation(self, db_session: Session) -> None:
        """MonitoringConfig factory creates a valid record with correct fields."""
        world = make_world(db_session)
        ss = make_signal_source(db_session, account_id=world.account.id)
        mc = make_monitoring_config(
            db_session, project_id=world.project.id, signal_source_id=ss.id
        )

        result = db_session.execute(
            select(MonitoringConfig).where(MonitoringConfig.id == mc.id)
        ).scalar_one()

        assert result.project_id == world.project.id
        assert result.signal_source_id == ss.id
        assert result.name.startswith("test-monitor-")
        assert result.rules == {"prompt": "Check for cleanliness"}
        assert result.enabled is True

    def test_monitoring_config_project_isolation(self, db_session: Session) -> None:
        """Configs from project A not visible when querying project B."""
        world_a = make_world(db_session)
        world_b = make_world(db_session)
        ss_a = make_signal_source(db_session, account_id=world_a.account.id)
        ss_b = make_signal_source(db_session, account_id=world_b.account.id)

        mc_a = make_monitoring_config(
            db_session, project_id=world_a.project.id, signal_source_id=ss_a.id
        )
        mc_b = make_monitoring_config(
            db_session, project_id=world_b.project.id, signal_source_id=ss_b.id
        )

        configs_a = (
            db_session.execute(
                select(MonitoringConfig).where(
                    MonitoringConfig.project_id == world_a.project.id
                )
            )
            .scalars()
            .all()
        )
        configs_b = (
            db_session.execute(
                select(MonitoringConfig).where(
                    MonitoringConfig.project_id == world_b.project.id
                )
            )
            .scalars()
            .all()
        )

        assert len(configs_a) == 1
        assert configs_a[0].id == mc_a.id
        assert len(configs_b) == 1
        assert configs_b[0].id == mc_b.id
        assert {c.id for c in configs_a}.isdisjoint({c.id for c in configs_b})

    def test_monitoring_run_linked_to_config(self, db_session: Session) -> None:
        """MonitoringRun correctly links to its config; JSONB fields round-trip."""
        world = make_world(db_session)
        ss = make_signal_source(db_session, account_id=world.account.id)
        mc = make_monitoring_config(
            db_session, project_id=world.project.id, signal_source_id=ss.id
        )
        mr = make_monitoring_run(
            db_session,
            monitoring_config_id=mc.id,
            trigger_metadata={"source": "lambda", "image_key": "s3://bucket/img.jpg"},
            evaluation_result={"result": "fail", "violations": ["dirty floor"]},
        )

        result = db_session.execute(
            select(MonitoringRun).where(MonitoringRun.id == mr.id)
        ).scalar_one()

        assert result.monitoring_config_id == mc.id
        assert result.trigger_metadata["source"] == "lambda"
        assert result.trigger_metadata["image_key"] == "s3://bucket/img.jpg"
        assert result.evaluation_result["result"] == "fail"
        assert result.evaluation_result["violations"] == ["dirty floor"]

    def test_monitoring_run_timestamps(self, db_session: Session) -> None:
        """MonitoringRun started_at and completed_at round-trip with timezone."""
        world = make_world(db_session)
        ss = make_signal_source(db_session, account_id=world.account.id)
        mc = make_monitoring_config(
            db_session, project_id=world.project.id, signal_source_id=ss.id
        )

        started = datetime(2026, 3, 1, 10, 0, 0, tzinfo=UTC)
        completed = datetime(2026, 3, 1, 10, 0, 5, tzinfo=UTC)
        mr = make_monitoring_run(
            db_session,
            monitoring_config_id=mc.id,
            started_at=started,
            completed_at=completed,
        )

        result = db_session.execute(
            select(MonitoringRun).where(MonitoringRun.id == mr.id)
        ).scalar_one()

        assert result.started_at == started
        assert result.completed_at == completed

    def test_signal_source_to_config_chain(self, db_session: Session) -> None:
        """Account -> SignalSource -> MonitoringConfig chain is consistent."""
        world = make_world(db_session)
        ss = make_signal_source(
            db_session, account_id=world.account.id, project_id=world.project.id
        )
        mc = make_monitoring_config(
            db_session, project_id=world.project.id, signal_source_id=ss.id
        )

        loaded_ss = db_session.execute(
            select(SignalSource).where(SignalSource.id == mc.signal_source_id)
        ).scalar_one()

        assert loaded_ss.account_id == world.account.id
        assert loaded_ss.project_id == world.project.id

    def test_signal_feed_linked_to_source(self, db_session: Session) -> None:
        """SignalFeed correctly links to its source with proper field values."""
        world = make_world(db_session)
        ss = make_signal_source(db_session, account_id=world.account.id)
        sf = make_signal_feed(db_session, source_id=ss.id)

        result = db_session.execute(
            select(SignalFeed).where(SignalFeed.id == sf.id)
        ).scalar_one()

        assert result.source_id == ss.id
        assert result.feed_type.value == "image_snapshot"
        assert result.capture_mode.value == "pull"
        assert result.status.value == "active"
        assert result.capture_count == 0


# ---------------------------------------------------------------------------
# MonitoringConfig Repository Tests (async — all data created via async_session)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestMonitoringConfigRepository:
    """Async repository tests for MonitoringConfigRepositoryAsync."""

    async def test_config_repo_crud_lifecycle(
        self, async_session: AsyncSession
    ) -> None:
        """Full CRUD lifecycle: create -> read -> update -> delete."""
        account_id, project_id = await _async_make_world(async_session)
        ss = await _async_make_signal_source(async_session, account_id=account_id)

        repo = MonitoringConfigRepositoryAsync(async_session)

        # Create
        config = MonitoringConfig(
            project_id=project_id,
            signal_source_id=ss.id,
            name="lifecycle-test",
            rules={"prompt": "Check counters"},
            enabled=True,
        )
        created = await repo.create(config)
        assert created.id is not None
        assert created.name == "lifecycle-test"

        # Read
        fetched = await repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.name == "lifecycle-test"

        # Update
        updated = await repo.update(
            created.id,
            name="lifecycle-updated",
            rules={"prompt": "Check floors"},
        )
        assert updated is not None
        assert updated.name == "lifecycle-updated"
        assert updated.rules == {"prompt": "Check floors"}

        # Delete
        deleted = await repo.delete(created.id)
        assert deleted is True

        gone = await repo.get_by_id(created.id)
        assert gone is None

    async def test_config_repo_get_by_project_enabled_filter(
        self, async_session: AsyncSession
    ) -> None:
        """get_by_project filters by enabled status correctly."""
        account_id, project_id = await _async_make_world(async_session)
        ss = await _async_make_signal_source(async_session, account_id=account_id)

        await _async_make_monitoring_config(
            async_session,
            project_id=project_id,
            signal_source_id=ss.id,
            enabled=True,
            name="enabled-config",
        )
        await _async_make_monitoring_config(
            async_session,
            project_id=project_id,
            signal_source_id=ss.id,
            enabled=False,
            name="disabled-config",
        )

        repo = MonitoringConfigRepositoryAsync(async_session)

        enabled = await repo.get_by_project(project_id, enabled=True)
        assert len(enabled) == 1
        assert enabled[0].name == "enabled-config"

        disabled = await repo.get_by_project(project_id, enabled=False)
        assert len(disabled) == 1
        assert disabled[0].name == "disabled-config"

        all_configs = await repo.get_by_project(project_id)
        assert len(all_configs) == 2

    async def test_config_repo_get_by_name(self, async_session: AsyncSession) -> None:
        """get_by_name finds config by project_id + name, returns None for miss."""
        account_id, project_id = await _async_make_world(async_session)
        ss = await _async_make_signal_source(async_session, account_id=account_id)

        await _async_make_monitoring_config(
            async_session,
            project_id=project_id,
            signal_source_id=ss.id,
            name="unique-name",
        )

        repo = MonitoringConfigRepositoryAsync(async_session)

        found = await repo.get_by_name(project_id, "unique-name")
        assert found is not None
        assert found.name == "unique-name"

        missing = await repo.get_by_name(project_id, "nonexistent")
        assert missing is None

    async def test_config_repo_get_by_project_signal_source_filter(
        self, async_session: AsyncSession
    ) -> None:
        """get_by_project filters by signal_source_id correctly."""
        account_id, project_id = await _async_make_world(async_session)
        ss_a = await _async_make_signal_source(async_session, account_id=account_id)
        ss_b = await _async_make_signal_source(async_session, account_id=account_id)

        await _async_make_monitoring_config(
            async_session,
            project_id=project_id,
            signal_source_id=ss_a.id,
            name="config-source-a",
        )
        await _async_make_monitoring_config(
            async_session,
            project_id=project_id,
            signal_source_id=ss_b.id,
            name="config-source-b",
        )

        repo = MonitoringConfigRepositoryAsync(async_session)

        results_a = await repo.get_by_project(project_id, signal_source_id=ss_a.id)
        assert len(results_a) == 1
        assert results_a[0].name == "config-source-a"

        results_b = await repo.get_by_project(project_id, signal_source_id=ss_b.id)
        assert len(results_b) == 1
        assert results_b[0].name == "config-source-b"

    async def test_config_repo_delete_nonexistent(
        self, async_session: AsyncSession
    ) -> None:
        """Deleting a non-existent config returns False."""
        repo = MonitoringConfigRepositoryAsync(async_session)
        result = await repo.delete(uuid.uuid4())
        assert result is False


# ---------------------------------------------------------------------------
# MonitoringRun Repository Tests (async — all data created via async_session)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestMonitoringRunRepository:
    """Async repository tests for MonitoringRunRepositoryAsync."""

    async def test_run_repo_create_and_get(self, async_session: AsyncSession) -> None:
        """Create a run via repository and read it back."""
        account_id, project_id = await _async_make_world(async_session)
        ss = await _async_make_signal_source(async_session, account_id=account_id)
        mc = await _async_make_monitoring_config(
            async_session, project_id=project_id, signal_source_id=ss.id
        )

        repo = MonitoringRunRepositoryAsync(async_session)
        now = datetime.now(UTC)
        run = MonitoringRun(
            monitoring_config_id=mc.id,
            trigger_metadata={"source": "test", "key": "value"},
            started_at=now,
            evaluation_result={"result": "pass", "score": 95},
        )
        created = await repo.create(run)
        assert created.id is not None

        fetched = await repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.monitoring_config_id == mc.id
        assert fetched.trigger_metadata["key"] == "value"
        assert fetched.evaluation_result["score"] == 95

    async def test_run_repo_get_by_config_ordering(
        self, async_session: AsyncSession
    ) -> None:
        """get_by_config returns runs in descending started_at order."""
        account_id, project_id = await _async_make_world(async_session)
        ss = await _async_make_signal_source(async_session, account_id=account_id)
        mc = await _async_make_monitoring_config(
            async_session, project_id=project_id, signal_source_id=ss.id
        )

        base = datetime(2026, 3, 1, 10, 0, 0, tzinfo=UTC)
        await _async_make_monitoring_run(
            async_session, monitoring_config_id=mc.id, started_at=base
        )
        await _async_make_monitoring_run(
            async_session,
            monitoring_config_id=mc.id,
            started_at=base + timedelta(hours=2),
        )
        await _async_make_monitoring_run(
            async_session,
            monitoring_config_id=mc.id,
            started_at=base + timedelta(hours=1),
        )

        repo = MonitoringRunRepositoryAsync(async_session)
        runs = await repo.get_by_config(mc.id)

        assert len(runs) == 3
        # Most recent first
        assert runs[0].started_at > runs[1].started_at > runs[2].started_at

    async def test_run_repo_get_by_config_date_filter(
        self, async_session: AsyncSession
    ) -> None:
        """get_by_config filters by start_date and end_date."""
        account_id, project_id = await _async_make_world(async_session)
        ss = await _async_make_signal_source(async_session, account_id=account_id)
        mc = await _async_make_monitoring_config(
            async_session, project_id=project_id, signal_source_id=ss.id
        )

        day1 = datetime(2026, 3, 1, 10, 0, 0, tzinfo=UTC)
        day2 = datetime(2026, 3, 2, 10, 0, 0, tzinfo=UTC)
        day3 = datetime(2026, 3, 3, 10, 0, 0, tzinfo=UTC)

        await _async_make_monitoring_run(
            async_session, monitoring_config_id=mc.id, started_at=day1
        )
        await _async_make_monitoring_run(
            async_session, monitoring_config_id=mc.id, started_at=day2
        )
        await _async_make_monitoring_run(
            async_session, monitoring_config_id=mc.id, started_at=day3
        )

        repo = MonitoringRunRepositoryAsync(async_session)

        # Only day2
        filtered = await repo.get_by_config(mc.id, start_date=day2, end_date=day2)
        assert len(filtered) == 1
        assert filtered[0].started_at == day2

        # day1 and day2
        filtered2 = await repo.get_by_config(mc.id, start_date=day1, end_date=day2)
        assert len(filtered2) == 2

    async def test_run_repo_get_by_config_result_filter(
        self, async_session: AsyncSession
    ) -> None:
        """get_by_config filters by evaluation_result JSONB 'result' key."""
        account_id, project_id = await _async_make_world(async_session)
        ss = await _async_make_signal_source(async_session, account_id=account_id)
        mc = await _async_make_monitoring_config(
            async_session, project_id=project_id, signal_source_id=ss.id
        )

        now = datetime.now(UTC)
        await _async_make_monitoring_run(
            async_session,
            monitoring_config_id=mc.id,
            started_at=now,
            evaluation_result={"result": "pass"},
        )
        await _async_make_monitoring_run(
            async_session,
            monitoring_config_id=mc.id,
            started_at=now + timedelta(minutes=1),
            evaluation_result={"result": "fail"},
        )
        await _async_make_monitoring_run(
            async_session,
            monitoring_config_id=mc.id,
            started_at=now + timedelta(minutes=2),
            evaluation_result={"result": "pass"},
        )

        repo = MonitoringRunRepositoryAsync(async_session)

        pass_runs = await repo.get_by_config(mc.id, result_filter="pass")
        assert len(pass_runs) == 2
        assert all(r.evaluation_result["result"] == "pass" for r in pass_runs)

        fail_runs = await repo.get_by_config(mc.id, result_filter="fail")
        assert len(fail_runs) == 1

    async def test_run_repo_delete_batch(self, async_session: AsyncSession) -> None:
        """delete_batch removes specified runs and reports counts."""
        account_id, project_id = await _async_make_world(async_session)
        ss = await _async_make_signal_source(async_session, account_id=account_id)
        mc = await _async_make_monitoring_config(
            async_session, project_id=project_id, signal_source_id=ss.id
        )

        now = datetime.now(UTC)
        r1 = await _async_make_monitoring_run(
            async_session, monitoring_config_id=mc.id, started_at=now
        )
        r2 = await _async_make_monitoring_run(
            async_session,
            monitoring_config_id=mc.id,
            started_at=now + timedelta(minutes=1),
        )
        r3 = await _async_make_monitoring_run(
            async_session,
            monitoring_config_id=mc.id,
            started_at=now + timedelta(minutes=2),
        )

        repo = MonitoringRunRepositoryAsync(async_session)
        result = await repo.delete_batch([r1.id, r2.id])

        assert result == {"deleted": 2, "not_found": 0}

        # r3 still exists
        remaining = await repo.get_by_id(r3.id)
        assert remaining is not None

        # r1 and r2 gone
        assert await repo.get_by_id(r1.id) is None
        assert await repo.get_by_id(r2.id) is None
