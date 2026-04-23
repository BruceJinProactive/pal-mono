"""Tests for db.pal_repository.AnalyticsRepository and analytics data classes.

Validates data class immutability and the repository session holder.
"""

import uuid
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from unittest.mock import AsyncMock

import pytest

from db.pal_repository.analytics import AnalyticsRepository
from db.pal_repository.data_classes.analytics import (
    ActiveUsersRow,
    CallsInfoSummaryRow,
    CallsTimeSummaryRow,
    ConversionSummaryRow,
    TurnsSummaryRow,
)


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> AnalyticsRepository:
    return AnalyticsRepository(mock_session)


# ---------------------------------------------------------------------------
# AnalyticsRepository
# ---------------------------------------------------------------------------


class TestInit:
    def test_repository_accepts_session(self, mock_session: AsyncMock) -> None:
        repo = AnalyticsRepository(mock_session)
        assert repo.session is mock_session


# ---------------------------------------------------------------------------
# ActiveUsersRow
# ---------------------------------------------------------------------------


class TestActiveUsersRow:
    def test_creates_row(self) -> None:
        row = ActiveUsersRow(active_users=10, conversations=25)
        assert row.active_users == 10
        assert row.conversations == 25
        assert row.account_id is None
        assert row.date is None

    def test_creates_row_with_optional_fields(self) -> None:
        acct_id = uuid.uuid4()
        proj_id = uuid.uuid4()
        row = ActiveUsersRow(
            active_users=5,
            conversations=12,
            account_id=acct_id,
            account_name="Test Account",
            project_id=proj_id,
            project_name="Test Project",
            date=date(2025, 6, 1),
        )
        assert row.account_id == acct_id
        assert row.project_name == "Test Project"
        assert row.date == date(2025, 6, 1)

    def test_frozen(self) -> None:
        row = ActiveUsersRow(active_users=10, conversations=25)
        with pytest.raises(AttributeError):
            row.active_users = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TurnsSummaryRow
# ---------------------------------------------------------------------------


class TestTurnsSummaryRow:
    def test_creates_row(self) -> None:
        row = TurnsSummaryRow(
            low_turns=3, high_turns=10, total_convs=50, total_turns=200
        )
        assert row.low_turns == 3
        assert row.total_turns == 200

    def test_frozen(self) -> None:
        row = TurnsSummaryRow(
            low_turns=3, high_turns=10, total_convs=50, total_turns=200
        )
        with pytest.raises(AttributeError):
            row.total_turns = 999  # type: ignore[misc]


# ---------------------------------------------------------------------------
# CallsTimeSummaryRow
# ---------------------------------------------------------------------------


class TestCallsTimeSummaryRow:
    def test_creates_row(self) -> None:
        row = CallsTimeSummaryRow(
            total_calls=100,
            avg_duration=45.5,
            avg_turn_latency=1.2,
            short_calls=20,
            long_calls=10,
            transfer_calls=5,
            transfer_rate=0.05,
            positive_calls=60,
            neutral_calls=30,
            negative_calls=10,
        )
        assert row.total_calls == 100
        assert row.transfer_rate == 0.05

    def test_frozen(self) -> None:
        row = CallsTimeSummaryRow(
            total_calls=100,
            avg_duration=None,
            avg_turn_latency=None,
            short_calls=20,
            long_calls=10,
            transfer_calls=5,
            transfer_rate=None,
            positive_calls=60,
            neutral_calls=30,
            negative_calls=10,
        )
        with pytest.raises(AttributeError):
            row.total_calls = 0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# CallsInfoSummaryRow
# ---------------------------------------------------------------------------


class TestCallsInfoSummaryRow:
    def test_creates_row(self) -> None:
        row = CallsInfoSummaryRow(
            purpose_counts={"ordering": 5, "inquiry": 3},
            language_counts={"en": 7, "es": 1},
        )
        assert row.purpose_counts["ordering"] == 5
        assert row.language_counts["en"] == 7

    def test_dicts_are_immutable(self) -> None:
        row = CallsInfoSummaryRow(
            purpose_counts={"ordering": 5},
            language_counts={"en": 7},
        )
        assert isinstance(row.purpose_counts, MappingProxyType)
        assert isinstance(row.language_counts, MappingProxyType)
        with pytest.raises(TypeError):
            row.purpose_counts["new_key"] = 99  # type: ignore[index]

    def test_defensive_copy(self) -> None:
        original = {"ordering": 5}
        row = CallsInfoSummaryRow(
            purpose_counts=original,
            language_counts={"en": 7},
        )
        original["ordering"] = 999
        assert row.purpose_counts["ordering"] == 5

    def test_frozen(self) -> None:
        row = CallsInfoSummaryRow(
            purpose_counts={"ordering": 5},
            language_counts={"en": 7},
        )
        with pytest.raises(AttributeError):
            row.purpose_counts = {}  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ConversionSummaryRow
# ---------------------------------------------------------------------------


class TestConversionSummaryRow:
    def test_creates_row(self) -> None:
        row = ConversionSummaryRow(
            total_conversations=100,
            conversations_with_orders=40,
            paid_orders=30,
            total_subtotal=Decimal("1500.00"),
            paid_total=Decimal("1200.00"),
            total_reservations=10,
            total_waitlists=5,
        )
        assert row.total_conversations == 100
        assert row.paid_total == Decimal("1200.00")

    def test_frozen(self) -> None:
        row = ConversionSummaryRow(
            total_conversations=100,
            conversations_with_orders=40,
            paid_orders=30,
            total_subtotal=Decimal("1500.00"),
            paid_total=Decimal("1200.00"),
            total_reservations=10,
            total_waitlists=5,
        )
        with pytest.raises(AttributeError):
            row.paid_orders = 0  # type: ignore[misc]
