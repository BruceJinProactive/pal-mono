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
    session.refresh = AsyncMock()
    return session


class TestCreateSetsResultColumns:
    """Tests that create() persists result/details/confidence from the MonitoringRun object."""

    @pytest.mark.asyncio
    async def test_create_preserves_result_columns(
        self, mock_session: AsyncMock
    ) -> None:
        """create() should flush and refresh a run that carries result/details/confidence."""
        repo = MonitoringRunRepositoryAsync(mock_session)

        run = MagicMock()
        run.result = "pass"
        run.details = "All clear"
        run.confidence = 95

        mock_session.refresh = AsyncMock()
        result = await repo.create(run)

        mock_session.add.assert_called_once_with(run)
        mock_session.flush.assert_awaited_once()
        mock_session.refresh.assert_awaited_once_with(run)
        assert result is run

    @pytest.mark.asyncio
    async def test_create_preserves_none_result_columns(
        self, mock_session: AsyncMock
    ) -> None:
        """create() should work when result/details/confidence are None."""
        repo = MonitoringRunRepositoryAsync(mock_session)

        run = MagicMock()
        run.result = None
        run.details = None
        run.confidence = None

        result = await repo.create(run)

        mock_session.add.assert_called_once_with(run)
        assert result is run


class TestUpdateSetsResultColumns:
    """Tests that update() correctly applies result/details/confidence kwargs."""

    @pytest.mark.asyncio
    async def test_update_sets_result_details_confidence(
        self, mock_session: AsyncMock
    ) -> None:
        """update() should set result, details, and confidence via setattr."""
        repo = MonitoringRunRepositoryAsync(mock_session)
        run_id = uuid.uuid4()

        mock_run = MagicMock()
        mock_run.result = None
        mock_run.details = None
        mock_run.confidence = None

        with patch.object(
            repo, "get_by_id", new_callable=AsyncMock, return_value=mock_run
        ):
            updated = await repo.update(
                run_id,
                result="fail",
                details="Anomaly detected",
                confidence=87,
                evaluation_result={"result": "fail"},
            )

        assert updated is mock_run
        assert mock_run.result == "fail"
        assert mock_run.details == "Anomaly detected"
        assert mock_run.confidence == 87

    @pytest.mark.asyncio
    async def test_update_clears_confidence_on_error(
        self, mock_session: AsyncMock
    ) -> None:
        """update() should set confidence to None when updating to error status."""
        repo = MonitoringRunRepositoryAsync(mock_session)
        run_id = uuid.uuid4()

        mock_run = MagicMock()
        mock_run.result = "pass"
        mock_run.details = "All clear"
        mock_run.confidence = 95

        with patch.object(
            repo, "get_by_id", new_callable=AsyncMock, return_value=mock_run
        ):
            await repo.update(
                run_id,
                result="error",
                details="Rerun failed: timeout",
                confidence=None,
            )

        assert mock_run.result == "error"
        assert mock_run.details == "Rerun failed: timeout"
        assert mock_run.confidence is None

    @pytest.mark.asyncio
    async def test_update_returns_none_for_missing_run(
        self, mock_session: AsyncMock
    ) -> None:
        """update() should return None when run does not exist."""
        repo = MonitoringRunRepositoryAsync(mock_session)

        with patch.object(repo, "get_by_id", new_callable=AsyncMock, return_value=None):
            result = await repo.update(
                uuid.uuid4(), result="pass", details="ok", confidence=90
            )

        assert result is None


class TestGetByConfigResultFilter:
    """Tests that get_by_config filters by the result column in SQL."""

    @pytest.mark.asyncio
    async def test_result_filter_is_applied(self, mock_session: AsyncMock) -> None:
        """get_by_config() should include result filter in the SQL query."""
        repo = MonitoringRunRepositoryAsync(mock_session)
        config_id = uuid.uuid4()

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        runs = await repo.get_by_config(config_id, result_filter="pass")

        assert runs == []
        mock_session.execute.assert_awaited_once()

        # Verify the compiled query contains a coalesce fallback to JSONB
        executed_query = mock_session.execute.call_args[0][0]
        compiled = str(executed_query.compile(compile_kwargs={"literal_binds": True}))
        assert "coalesce" in compiled.lower()
        assert "monitoring_runs.result" in compiled
        assert "evaluation_result" in compiled

    @pytest.mark.asyncio
    async def test_no_result_filter_omits_clause(self, mock_session: AsyncMock) -> None:
        """get_by_config() should not filter by result when result_filter is None."""
        repo = MonitoringRunRepositoryAsync(mock_session)
        config_id = uuid.uuid4()

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        await repo.get_by_config(config_id, result_filter=None)

        executed_query = mock_session.execute.call_args[0][0]
        compiled = str(executed_query.compile(compile_kwargs={"literal_binds": True}))
        # result column appears in SELECT but should NOT appear in WHERE
        where_clause = compiled.split("WHERE", 1)[1] if "WHERE" in compiled else ""
        assert "monitoring_runs.result" not in where_clause

    @pytest.mark.asyncio
    async def test_get_by_config_error_returns_empty_list(
        self, mock_session: AsyncMock
    ) -> None:
        """get_by_config() should return empty list on SQLAlchemyError."""
        repo = MonitoringRunRepositoryAsync(mock_session)
        mock_session.execute.side_effect = SQLAlchemyError("query failed")

        runs = await repo.get_by_config(uuid.uuid4(), result_filter="pass")

        assert runs == []
        mock_session.rollback.assert_awaited_once()


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


class TestGetSummaryByTags:
    """Tests for get_summary_by_tags() query construction and error handling."""

    @pytest.mark.asyncio
    async def test_returns_rows_on_success(self, mock_session: AsyncMock) -> None:
        """get_summary_by_tags() executes query and returns all rows."""
        repo = MonitoringRunRepositoryAsync(mock_session)
        project_id = uuid.uuid4()

        mock_row = MagicMock()
        mock_row.tag = "Food"
        mock_row.total_runs = 10
        mock_row.pass_count = 5
        mock_row.fail_count = 3
        mock_row.error_count = 2

        mock_result = MagicMock()
        mock_result.all.return_value = [mock_row]
        mock_session.execute.return_value = mock_result

        rows = await repo.get_summary_by_tags(project_id=project_id)

        assert len(rows) == 1
        assert rows[0].tag == "Food"
        mock_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_query_contains_unnest_and_cardinality(
        self, mock_session: AsyncMock
    ) -> None:
        """Query uses unnest for tags and cardinality > 0 filter."""
        repo = MonitoringRunRepositoryAsync(mock_session)

        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute.return_value = mock_result

        await repo.get_summary_by_tags(project_id=uuid.uuid4())

        executed_query = mock_session.execute.call_args[0][0]
        compiled = str(executed_query.compile(compile_kwargs={"literal_binds": True}))
        assert "unnest" in compiled.lower()
        assert "cardinality" in compiled.lower()

    @pytest.mark.asyncio
    async def test_date_filters_applied(self, mock_session: AsyncMock) -> None:
        """Query includes started_at filters when dates provided."""
        repo = MonitoringRunRepositoryAsync(mock_session)
        from datetime import datetime, timezone

        start = datetime(2026, 4, 1, tzinfo=timezone.utc)
        end = datetime(2026, 4, 14, tzinfo=timezone.utc)

        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute.return_value = mock_result

        await repo.get_summary_by_tags(
            project_id=uuid.uuid4(), start_date=start, end_date=end
        )

        executed_query = mock_session.execute.call_args[0][0]
        compiled = str(executed_query.compile(compile_kwargs={"literal_binds": True}))
        assert "started_at" in compiled

    @pytest.mark.asyncio
    async def test_skipped_excluded(self, mock_session: AsyncMock) -> None:
        """Query filters out skipped results."""
        repo = MonitoringRunRepositoryAsync(mock_session)

        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute.return_value = mock_result

        await repo.get_summary_by_tags(project_id=uuid.uuid4())

        executed_query = mock_session.execute.call_args[0][0]
        compiled = str(executed_query.compile(compile_kwargs={"literal_binds": True}))
        assert "skipped" in compiled.lower()

    @pytest.mark.asyncio
    async def test_returns_empty_on_sqlalchemy_error(
        self, mock_session: AsyncMock
    ) -> None:
        """get_summary_by_tags() returns empty list on SQLAlchemyError."""
        repo = MonitoringRunRepositoryAsync(mock_session)
        mock_session.execute.side_effect = SQLAlchemyError("query failed")

        rows = await repo.get_summary_by_tags(project_id=uuid.uuid4())

        assert rows == []
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
