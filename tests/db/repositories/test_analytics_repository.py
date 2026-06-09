"""Tests for AnalyticsRepository billing exclusion filters.

Exercises the exclude_eval_calls and exclude_caller_numbers code paths
in get_calls_time_summary and get_conversion_summary.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

from sqlalchemy.exc import SQLAlchemyError

from db.repositories.analytics_repository import AnalyticsRepository


def _make_session() -> MagicMock:
    """Create a mock session that returns empty results from execute."""
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    session.execute.return_value = mock_result
    return session


class TestGetCallsTimeSummaryExclusions:
    """Tests for exclusion filters in get_calls_time_summary."""

    def test_exclude_eval_calls_adds_filter(self) -> None:
        """Should execute without error when exclude_eval_calls=True."""
        session = _make_session()
        repo = AnalyticsRepository(session)

        result = repo.get_calls_time_summary(
            start_date=datetime(2026, 4, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 4, 30, tzinfo=timezone.utc),
            group_by=[],
            filter_by={"account_id": uuid.uuid4()},
            exclude_eval_calls=True,
        )

        assert result == []
        session.execute.assert_called_once()

    def test_exclude_caller_numbers_adds_filter(self) -> None:
        """Should execute without error when exclude_caller_numbers is provided."""
        session = _make_session()
        repo = AnalyticsRepository(session)

        result = repo.get_calls_time_summary(
            start_date=datetime(2026, 4, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 4, 30, tzinfo=timezone.utc),
            group_by=[],
            filter_by={"account_id": uuid.uuid4()},
            exclude_caller_numbers=["+18889738742", "+15551234567"],
        )

        assert result == []
        session.execute.assert_called_once()

    def test_both_exclusions_together(self) -> None:
        """Should execute without error when both exclusions are active."""
        session = _make_session()
        repo = AnalyticsRepository(session)

        result = repo.get_calls_time_summary(
            start_date=datetime(2026, 4, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 4, 30, tzinfo=timezone.utc),
            group_by=[],
            filter_by={"account_id": uuid.uuid4()},
            exclude_eval_calls=True,
            exclude_caller_numbers=["+18889738742"],
        )

        assert result == []
        session.execute.assert_called_once()


class TestGetConversionSummaryExclusions:
    """Tests for exclusion filters in get_conversion_summary."""

    def test_exclude_eval_calls_adds_filter(self) -> None:
        """Should execute without error when exclude_eval_calls=True."""
        session = _make_session()
        repo = AnalyticsRepository(session)

        result = repo.get_conversion_summary(
            start_date=datetime(2026, 4, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 4, 30, tzinfo=timezone.utc),
            group_by=[],
            filter_by={"account_id": uuid.uuid4()},
            exclude_eval_calls=True,
        )

        assert result == []
        session.execute.assert_called_once()

    def test_exclude_caller_numbers_adds_filter(self) -> None:
        """Should execute without error when exclude_caller_numbers is provided."""
        session = _make_session()
        repo = AnalyticsRepository(session)

        result = repo.get_conversion_summary(
            start_date=datetime(2026, 4, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 4, 30, tzinfo=timezone.utc),
            group_by=[],
            filter_by={"account_id": uuid.uuid4()},
            exclude_caller_numbers=["+18889738742"],
        )

        assert result == []
        session.execute.assert_called_once()

    def test_both_exclusions_together(self) -> None:
        """Should execute without error when both exclusions are active."""
        session = _make_session()
        repo = AnalyticsRepository(session)

        result = repo.get_conversion_summary(
            start_date=datetime(2026, 4, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 4, 30, tzinfo=timezone.utc),
            group_by=[],
            filter_by={"account_id": uuid.uuid4()},
            exclude_eval_calls=True,
            exclude_caller_numbers=["+18889738742"],
        )

        assert result == []
        session.execute.assert_called_once()


class TestOrderingCapability:
    """Tests for ordering capability detection helpers."""

    def test_project_filter_conditions_empty_when_no_projects(self) -> None:
        repo = AnalyticsRepository(MagicMock())

        assert repo._project_filter_conditions(None) == []

    def test_project_filter_conditions_builds_project_clause(self) -> None:
        repo = AnalyticsRepository(MagicMock())

        conditions = repo._project_filter_conditions([uuid.uuid4()])

        assert len(conditions) == 1

    def test_has_ordering_enabled_returns_true_for_capability(self) -> None:
        session = MagicMock()
        capability_result = MagicMock()
        capability_result.first.return_value = object()
        session.execute.return_value = capability_result
        repo = AnalyticsRepository(session)

        assert repo.has_ordering_enabled(uuid.uuid4()) is True

        session.execute.assert_called_once()

    def test_has_ordering_enabled_returns_true_for_project_integration(self) -> None:
        session = MagicMock()
        capability_result = MagicMock()
        capability_result.first.return_value = None
        project_integration_result = MagicMock()
        project_integration_result.first.return_value = object()
        session.execute.side_effect = [
            capability_result,
            project_integration_result,
        ]
        repo = AnalyticsRepository(session)

        assert repo.has_ordering_enabled(uuid.uuid4(), [uuid.uuid4()]) is True

        assert session.execute.call_count == 2

    def test_has_ordering_enabled_returns_true_for_raw_config_tool(self) -> None:
        session = MagicMock()
        capability_result = MagicMock()
        capability_result.first.return_value = None
        project_integration_result = MagicMock()
        project_integration_result.first.return_value = None
        raw_config_result = MagicMock()
        raw_config_result.first.return_value = object()
        session.execute.side_effect = [
            capability_result,
            project_integration_result,
            raw_config_result,
        ]
        repo = AnalyticsRepository(session)

        assert repo.has_ordering_enabled(uuid.uuid4()) is True

        assert session.execute.call_count == 3

    def test_has_ordering_enabled_rolls_back_on_sqlalchemy_error(self) -> None:
        session = MagicMock()
        session.execute.side_effect = SQLAlchemyError("boom")
        repo = AnalyticsRepository(session)

        assert repo.has_ordering_enabled(uuid.uuid4()) is False

        session.rollback.assert_called_once()


class TestOrderAccuracyTimeSeries:
    """Tests for ordering dashboard accuracy aggregation query."""

    def test_get_order_accuracy_time_series_returns_rows(self) -> None:
        session = _make_session()
        row_date = datetime(2026, 5, 1, tzinfo=timezone.utc).date()
        session.execute.return_value.all.return_value = [(row_date, 2, 1)]
        repo = AnalyticsRepository(session)

        result = repo.get_order_accuracy_time_series(
            account_id=uuid.uuid4(),
            start_date=datetime(2026, 5, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 5, 2, tzinfo=timezone.utc),
            project_ids=[uuid.uuid4()],
        )

        assert result == [(row_date, 2, 1)]
        session.execute.assert_called_once()

    def test_get_order_accuracy_time_series_rolls_back_on_sqlalchemy_error(
        self,
    ) -> None:
        session = MagicMock()
        session.execute.side_effect = SQLAlchemyError("boom")
        repo = AnalyticsRepository(session)

        result = repo.get_order_accuracy_time_series(
            account_id=uuid.uuid4(),
            start_date=datetime(2026, 5, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 5, 2, tzinfo=timezone.utc),
        )

        assert result == []
        session.rollback.assert_called_once()
