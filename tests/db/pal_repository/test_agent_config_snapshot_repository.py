"""Tests for db.pal_repository.AgentConfigSnapshotRepository."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.pal_repository.agent_config_snapshot import AgentConfigSnapshotRepository
from db.pal_repository.data_classes.agent_config_snapshot import AgentConfigSnapshotData


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> AgentConfigSnapshotRepository:
    return AgentConfigSnapshotRepository(mock_session)


@pytest.fixture
def sample_orm_row() -> MagicMock:
    row = MagicMock()
    row.fingerprint = "abc123hash"
    row.agent_id = uuid.uuid4()
    row.project_id = uuid.uuid4()
    row.system_prompt_hash = "hash123"
    row.system_prompt_text = "You are helpful."
    row.first_seen_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.last_seen_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.config_snapshot = {"model": "gpt-4", "nested": {"key": "value"}}
    return row


class TestGetByFingerprint:

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: AgentConfigSnapshotRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        data = await repo.get_by_fingerprint("abc123hash")
        assert isinstance(data, AgentConfigSnapshotData)
        assert data.fingerprint == "abc123hash"
        assert data.config_snapshot["model"] == "gpt-4"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: AgentConfigSnapshotRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        assert await repo.get_by_fingerprint("unknown") is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: AgentConfigSnapshotRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("connection lost")
        with pytest.raises(RuntimeError, match="connection lost"):
            await repo.get_by_fingerprint("abc")


class TestGetByAgentId:

    @pytest.mark.asyncio
    async def test_returns_list(
        self,
        repo: AgentConfigSnapshotRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        results = await repo.get_by_agent_id(uuid.uuid4())
        assert isinstance(results, list)
        assert len(results) == 1
        assert results[0].fingerprint == "abc123hash"

    @pytest.mark.asyncio
    async def test_returns_empty_list(
        self, repo: AgentConfigSnapshotRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        results = await repo.get_by_agent_id(uuid.uuid4())
        assert results == []

    @pytest.mark.asyncio
    async def test_exception_propagates(
        self, repo: AgentConfigSnapshotRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("db error")
        with pytest.raises(RuntimeError, match="db error"):
            await repo.get_by_agent_id(uuid.uuid4())


class TestDataImmutability:

    def test_session_stored(
        self, repo: AgentConfigSnapshotRepository, mock_session: AsyncMock
    ) -> None:
        assert repo.session is mock_session

    def test_data_is_frozen(self) -> None:
        """Verify AgentConfigSnapshotData cannot be mutated after creation."""
        data = AgentConfigSnapshotData(
            fingerprint="abc",
            agent_id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            system_prompt_hash="h",
            system_prompt_text="t",
            first_seen_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            last_seen_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            data.fingerprint = "changed"  # type: ignore[misc]

    def test_config_snapshot_is_immutable(self) -> None:
        """Verify config_snapshot dict cannot be mutated in place."""
        data = AgentConfigSnapshotData(
            fingerprint="abc",
            agent_id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            system_prompt_hash="h",
            system_prompt_text="t",
            first_seen_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            last_seen_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            config_snapshot={"model": "gpt-4", "nested": {"inner": "val"}},
        )
        with pytest.raises(TypeError):
            data.config_snapshot["new_key"] = "value"  # type: ignore[index]
        # Nested dicts are also frozen
        with pytest.raises(TypeError):
            data.config_snapshot["nested"]["mutate"] = "fail"  # type: ignore[index]

    def test_config_snapshot_none_handling(self) -> None:
        """Empty config_snapshot default works correctly."""
        data = AgentConfigSnapshotData(
            fingerprint="abc",
            agent_id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            system_prompt_hash="h",
            system_prompt_text="t",
            first_seen_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            last_seen_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        assert len(data.config_snapshot) == 0
