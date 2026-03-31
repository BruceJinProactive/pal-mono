"""Tests for AgentConfigSnapshotRepositoryAsync."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from db.repositories.agent_config_snapshot_repository import (
    AgentConfigSnapshotRepositoryAsync,
)


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> AgentConfigSnapshotRepositoryAsync:
    return AgentConfigSnapshotRepositoryAsync(mock_session)


def _make_snapshot(
    fingerprint: str = "abc123",
    first_seen_at: datetime | None = None,
    last_seen_at: datetime | None = None,
) -> MagicMock:
    snap = MagicMock()
    snap.fingerprint = fingerprint
    snap.agent_id = uuid.uuid4()
    snap.project_id = uuid.uuid4()
    snap.system_prompt_hash = "hashvalue"
    snap.system_prompt_text = "You are a helpful assistant."
    snap.config_snapshot = {}
    now = datetime.now(timezone.utc)
    snap.first_seen_at = first_seen_at if first_seen_at is not None else now
    snap.last_seen_at = last_seen_at if last_seen_at is not None else now
    return snap


# ---------------------------------------------------------------------------
# get_or_create
# ---------------------------------------------------------------------------


class TestGetOrCreate:
    @pytest.mark.asyncio
    async def test_new_fingerprint_returns_created_true(
        self, repo: AgentConfigSnapshotRepositoryAsync, mock_session: AsyncMock
    ) -> None:
        now = datetime.now(timezone.utc)
        snap = _make_snapshot(fingerprint="fp_new", first_seen_at=now, last_seen_at=now)

        mock_execute_result = MagicMock()
        # get_or_create uses result.one() which returns (row, xmax)
        # xmax == 0 means freshly inserted
        mock_execute_result.one.return_value = (snap, 0)
        mock_session.execute.return_value = mock_execute_result

        result, created = await repo.get_or_create(snap)

        assert result is snap
        assert created is True
        mock_session.flush.assert_awaited_once()
        mock_session.refresh.assert_awaited_once_with(snap)

    @pytest.mark.asyncio
    async def test_existing_fingerprint_returns_created_false(
        self, repo: AgentConfigSnapshotRepositoryAsync, mock_session: AsyncMock
    ) -> None:
        first_seen = datetime(2025, 1, 1, tzinfo=timezone.utc)
        last_seen = datetime(2025, 6, 1, tzinfo=timezone.utc)
        snap = _make_snapshot(
            fingerprint="fp_existing",
            first_seen_at=first_seen,
            last_seen_at=last_seen,
        )

        mock_execute_result = MagicMock()
        # xmax != 0 means row already existed (conflict update)
        mock_execute_result.one.return_value = (snap, 1)
        mock_session.execute.return_value = mock_execute_result

        result, created = await repo.get_or_create(snap)

        assert result is snap
        assert created is False

    @pytest.mark.asyncio
    async def test_sqlalchemy_error_propagates_and_rolls_back(
        self, repo: AgentConfigSnapshotRepositoryAsync, mock_session: AsyncMock
    ) -> None:
        snap = _make_snapshot()
        mock_session.execute.side_effect = SQLAlchemyError("insert failed")

        with pytest.raises(SQLAlchemyError):
            await repo.get_or_create(snap)

        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_by_fingerprint
# ---------------------------------------------------------------------------


class TestGetByFingerprint:
    @pytest.mark.asyncio
    async def test_found_returns_snapshot(
        self, repo: AgentConfigSnapshotRepositoryAsync, mock_session: AsyncMock
    ) -> None:
        snap = _make_snapshot(fingerprint="fp_found")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = snap
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_fingerprint("fp_found")

        assert result is snap

    @pytest.mark.asyncio
    async def test_not_found_returns_none(
        self, repo: AgentConfigSnapshotRepositoryAsync, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_fingerprint("fp_missing")

        assert result is None

    @pytest.mark.asyncio
    async def test_sqlalchemy_error_returns_none(
        self, repo: AgentConfigSnapshotRepositoryAsync, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("db error")

        result = await repo.get_by_fingerprint("fp_error")

        assert result is None
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_by_agent_id
# ---------------------------------------------------------------------------


class TestGetByAgentId:
    @pytest.mark.asyncio
    async def test_returns_snapshots_ordered_by_first_seen_at_desc(
        self, repo: AgentConfigSnapshotRepositoryAsync, mock_session: AsyncMock
    ) -> None:
        agent_id = uuid.uuid4()
        snap1 = _make_snapshot(fingerprint="fp_1")
        snap2 = _make_snapshot(fingerprint="fp_2")
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [snap1, snap2]
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_agent_id(agent_id)

        assert result == [snap1, snap2]
        mock_session.execute.assert_awaited_once()

        # Verify the ORDER BY first_seen_at DESC is in the compiled statement
        executed_stmt = mock_session.execute.call_args[0][0]
        compiled = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "first_seen_at" in compiled.lower()
        assert "desc" in compiled.lower()

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_none_found(
        self, repo: AgentConfigSnapshotRepositoryAsync, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_agent_id(uuid.uuid4())

        assert result == []

    @pytest.mark.asyncio
    async def test_sqlalchemy_error_returns_empty_list(
        self, repo: AgentConfigSnapshotRepositoryAsync, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("db error")

        result = await repo.get_by_agent_id(uuid.uuid4())

        assert result == []
        mock_session.rollback.assert_awaited_once()
