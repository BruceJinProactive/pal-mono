"""Tests for AnalyticsRepository billing exclusion filters.

Exercises the exclude_eval_calls and exclude_caller_numbers code paths
in get_calls_time_summary and get_conversion_summary.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

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
