import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from services.analytics_service._implementation import (
    _build_ordering_filter_by,
    _to_date_key,
    get_ordering_metrics,
)


class _FakeAnalyticsRepository:
    def __init__(
        self,
        session: object,
        *,
        ordering_enabled: bool,
        conversion_rows: list[tuple],
        accuracy_rows: list[tuple],
    ) -> None:
        self.session = session
        self.ordering_enabled = ordering_enabled
        self.conversion_rows = conversion_rows
        self.accuracy_rows = accuracy_rows

    def has_ordering_enabled(
        self, account_id: uuid.UUID, project_ids: list[uuid.UUID] | None = None
    ) -> bool:
        return self.ordering_enabled

    def get_conversion_summary(
        self,
        start_date: datetime,
        end_date: datetime,
        group_by: list[str] | None = None,
        filter_by: dict[str, uuid.UUID | list[uuid.UUID]] | None = None,
    ) -> list[tuple]:
        return self.conversion_rows

    def get_order_accuracy_time_series(
        self,
        account_id: uuid.UUID,
        start_date: datetime,
        end_date: datetime,
        project_ids: list[uuid.UUID] | None = None,
    ) -> list[tuple]:
        return self.accuracy_rows


@pytest.mark.asyncio
async def test_ordering_metrics_disabled_returns_empty_series(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_repository(session: object) -> _FakeAnalyticsRepository:
        return _FakeAnalyticsRepository(
            session,
            ordering_enabled=False,
            conversion_rows=[],
            accuracy_rows=[],
        )

    monkeypatch.setattr(
        "services.analytics_service._implementation.db.AnalyticsRepository",
        fake_repository,
    )

    result = await get_ordering_metrics(
        session=MagicMock(),
        account_id=uuid.uuid4(),
        account_name="acme",
        start_date=datetime(2026, 5, 1, tzinfo=UTC),
        end_date=datetime(2026, 5, 2, 23, 59, 59, tzinfo=UTC),
    )

    assert result.ordering_enabled is False
    assert result.time_series == []
    assert result.summary.total_orders == 0
    assert result.summary.order_accuracy is None


@pytest.mark.asyncio
async def test_ordering_metrics_fills_dates_and_calculates_accuracy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversion_rows = [
        (
            datetime(2026, 5, 1, tzinfo=UTC).date(),
            9,  # total_conversations
            2,  # conversations_with_orders
            1,  # paid_orders
            Decimal("45.25"),  # total_subtotal
            Decimal("30.00"),  # paid_total
            0,  # total_reservations
            0,  # total_waitlists
        )
    ]
    accuracy_rows = [
        (
            datetime(2026, 5, 1, tzinfo=UTC).date(),
            2,
            1,
        )
    ]

    def fake_repository(session: object) -> _FakeAnalyticsRepository:
        return _FakeAnalyticsRepository(
            session,
            ordering_enabled=True,
            conversion_rows=conversion_rows,
            accuracy_rows=accuracy_rows,
        )

    monkeypatch.setattr(
        "services.analytics_service._implementation.db.AnalyticsRepository",
        fake_repository,
    )

    result = await get_ordering_metrics(
        session=MagicMock(),
        account_id=uuid.uuid4(),
        account_name="acme",
        start_date=datetime(2026, 5, 1, tzinfo=UTC),
        end_date=datetime(2026, 5, 2, 23, 59, 59, tzinfo=UTC),
    )

    assert result.ordering_enabled is True
    assert [point.date for point in result.time_series] == [
        "2026-05-01",
        "2026-05-02",
    ]
    assert result.time_series[0].total_orders == 2
    assert result.time_series[0].total_order_value == 45.25
    assert result.time_series[0].order_accuracy == 50.0
    assert result.time_series[0].tool_error_order_call_count == 1
    assert result.time_series[1].total_orders == 0
    assert result.time_series[1].order_accuracy is None
    assert result.summary.total_orders == 2
    assert result.summary.total_order_value == 45.25
    assert result.summary.order_accuracy == 50.0
    assert result.summary.tool_error_order_call_count == 1


def test_ordering_metrics_helpers_normalize_dates_and_filters() -> None:
    account_id = uuid.uuid4()
    project_id = uuid.uuid4()

    assert _to_date_key(datetime(2026, 5, 1, 12, 30, tzinfo=UTC)) == "2026-05-01"
    assert _to_date_key(datetime(2026, 5, 2, tzinfo=UTC).date()) == "2026-05-02"
    assert _to_date_key("2026-05-03T10:00:00+00:00") == "2026-05-03"
    assert _build_ordering_filter_by(account_id, None) == {"account_id": account_id}
    assert _build_ordering_filter_by(account_id, [project_id]) == {
        "account_id": account_id,
        "project_id": [project_id],
    }
