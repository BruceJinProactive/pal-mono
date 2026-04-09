"""Tests for MonitoringRunRepositoryAsync error handling paths."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from db.repositories.monitoring_run_repository import MonitoringRunRepositoryAsync


@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock()
    session.delete = AsyncMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    session.rollback = AsyncMock()
    return session


class TestDeleteRunsByConfigIdSuccess:
    """Tests for delete_runs_by_config_id() success path (line 194)."""

    @pytest.mark.asyncio
    async def test_delete_runs_by_config_id_returns_rowcount(
        self, mock_session: AsyncMock
    ) -> None:
        """delete_runs_by_config_id() returns rowcount on success."""
        repo = MonitoringRunRepositoryAsync(mock_session)
        config_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_session.execute.return_value = mock_result

        count = await repo.delete_runs_by_config_id(config_id)

        assert count == 5
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_runs_by_config_id_returns_zero_when_none_deleted(
        self, mock_session: AsyncMock
    ) -> None:
        """delete_runs_by_config_id() returns 0 when rowcount is 0 or None."""
        repo = MonitoringRunRepositoryAsync(mock_session)
        config_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result

        count = await repo.delete_runs_by_config_id(config_id)

        assert count == 0


class TestDeleteErrorHandling:
    """Tests for delete() SQLAlchemyError handling (line 172)."""

    @pytest.mark.asyncio
    async def test_delete_raises_on_sqlalchemy_error(
        self, mock_session: AsyncMock
    ) -> None:
        """delete() rolls back and re-raises when session.delete raises SQLAlchemyError."""
        repo = MonitoringRunRepositoryAsync(mock_session)
        run_id = uuid.uuid4()

        mock_run = MagicMock()
        with patch.object(
            repo, "get_by_id", new_callable=AsyncMock, return_value=mock_run
        ):
            mock_session.delete.side_effect = SQLAlchemyError("delete failed")

            with pytest.raises(SQLAlchemyError, match="delete failed"):
                await repo.delete(run_id)

        mock_session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_raises_on_flush_error(self, mock_session: AsyncMock) -> None:
        """delete() rolls back and re-raises when flush raises SQLAlchemyError."""
        repo = MonitoringRunRepositoryAsync(mock_session)
        run_id = uuid.uuid4()

        mock_run = MagicMock()
        with patch.object(
            repo, "get_by_id", new_callable=AsyncMock, return_value=mock_run
        ):
            mock_session.flush.side_effect = SQLAlchemyError("flush failed")

            with pytest.raises(SQLAlchemyError, match="flush failed"):
                await repo.delete(run_id)

        mock_session.rollback.assert_awaited_once()


class TestDeleteRunsByConfigIdErrorHandling:
    """Tests for delete_runs_by_config_id() SQLAlchemyError handling (lines 195-197)."""

    @pytest.mark.asyncio
    async def test_delete_runs_by_config_id_raises_on_execute_error(
        self, mock_session: AsyncMock
    ) -> None:
        """delete_runs_by_config_id() rolls back and re-raises on SQLAlchemyError."""
        repo = MonitoringRunRepositoryAsync(mock_session)
        config_id = uuid.uuid4()

        mock_session.execute.side_effect = SQLAlchemyError("execute failed")

        with pytest.raises(SQLAlchemyError, match="execute failed"):
            await repo.delete_runs_by_config_id(config_id)

        mock_session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_runs_by_config_id_raises_on_flush_error(
        self, mock_session: AsyncMock
    ) -> None:
        """delete_runs_by_config_id() rolls back and re-raises when flush fails."""
        repo = MonitoringRunRepositoryAsync(mock_session)
        config_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_session.execute.return_value = mock_result
        mock_session.flush.side_effect = SQLAlchemyError("flush failed")

        with pytest.raises(SQLAlchemyError, match="flush failed"):
            await repo.delete_runs_by_config_id(config_id)

        mock_session.rollback.assert_awaited_once()
