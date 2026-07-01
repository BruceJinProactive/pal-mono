import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from services.analytics_service._implementation import get_ordering_revenue_metrics


class _FakeAnalyticsRepository:
    def __init__(
        self,
        session: object,
        *,
        ordering_enabled: bool,
        daily_rows: list[dict[str, object]],
        store_rows: list[dict[str, object]],
    ) -> None:
        self.session = session
        self.ordering_enabled = ordering_enabled
        self.daily_rows = daily_rows
        self.store_rows = store_rows

    def has_ordering_enabled(
        self, account_id: uuid.UUID, project_ids: list[uuid.UUID] | None = None
    ) -> bool:
        return self.ordering_enabled

    def get_ordering_revenue_metrics(
        self,
        start_date: datetime,
        end_date: datetime,
        group_by: str | None = None,
        filter_by: dict[str, uuid.UUID | list[uuid.UUID]] | None = None,
    ) -> list[dict[str, object]]:
        if group_by == "date":
            return self.daily_rows
        if group_by == "store":
            return self.store_rows
        return []


@pytest.mark.asyncio
async def test_ordering_revenue_metrics_disabled_returns_empty_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_repository(session: object) -> _FakeAnalyticsRepository:
        return _FakeAnalyticsRepository(
            session,
            ordering_enabled=False,
            daily_rows=[],
            store_rows=[],
        )

    monkeypatch.setattr(
        "services.analytics_service._implementation.db.AnalyticsRepository",
        fake_repository,
    )

    result = await get_ordering_revenue_metrics(
        session=MagicMock(),
        account_id=uuid.uuid4(),
        account_name="acme",
        start_date=datetime(2026, 5, 1, tzinfo=UTC),
        end_date=datetime(2026, 5, 2, 23, 59, 59, tzinfo=UTC),
    )

    assert result.ordering_enabled is False
    assert result.summary.total_orders == 0
    assert result.summary.palona_revenue == 0.0
    assert result.time_series == []
    assert result.stores == []


@pytest.mark.asyncio
async def test_ordering_revenue_metrics_enabled_without_orders_returns_zero_time_series(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_repository(session: object) -> _FakeAnalyticsRepository:
        return _FakeAnalyticsRepository(
            session,
            ordering_enabled=True,
            daily_rows=[],
            store_rows=[],
        )

    monkeypatch.setattr(
        "services.analytics_service._implementation.db.AnalyticsRepository",
        fake_repository,
    )

    result = await get_ordering_revenue_metrics(
        session=MagicMock(),
        account_id=uuid.uuid4(),
        account_name="acme",
        start_date=datetime(2026, 5, 1, tzinfo=UTC),
        end_date=datetime(2026, 5, 2, 23, 59, 59, tzinfo=UTC),
    )

    assert result.ordering_enabled is True
    assert result.summary.total_orders == 0
    assert [point.date for point in result.time_series] == [
        "2026-05-01",
        "2026-05-02",
    ]
    assert all(point.total_orders == 0 for point in result.time_series)


@pytest.mark.asyncio
async def test_ordering_revenue_metrics_maps_summary_series_and_stores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = uuid.uuid4()
    daily_rows = [
        {
            "date": datetime(2026, 5, 1, tzinfo=UTC).date(),
            "total_orders": 4,
            "total_order_value": Decimal("120.00"),
            "palona_revenue": Decimal("75.00"),
            "payment_link_orders": 2,
            "payment_link_revenue": Decimal("50.00"),
            "pay_in_store_orders": 1,
            "pay_in_store_revenue": Decimal("25.00"),
            "takeout_orders": 3,
            "takeout_revenue": Decimal("70.00"),
            "delivery_orders": 1,
            "delivery_revenue": Decimal("30.00"),
        }
    ]
    store_rows = [
        {
            "store_id": "store-1",
            "project_id": project_id,
            "project_name": "Downtown",
            "total_orders": 4,
            "total_order_value": Decimal("120.00"),
            "palona_revenue": Decimal("75.00"),
            "payment_link_orders": 2,
            "payment_link_revenue": Decimal("50.00"),
            "pay_in_store_orders": 1,
            "pay_in_store_revenue": Decimal("25.00"),
            "takeout_orders": 3,
            "takeout_revenue": Decimal("70.00"),
            "delivery_orders": 1,
            "delivery_revenue": Decimal("30.00"),
        }
    ]

    def fake_repository(session: object) -> _FakeAnalyticsRepository:
        return _FakeAnalyticsRepository(
            session,
            ordering_enabled=True,
            daily_rows=daily_rows,
            store_rows=store_rows,
        )

    monkeypatch.setattr(
        "services.analytics_service._implementation.db.AnalyticsRepository",
        fake_repository,
    )

    result = await get_ordering_revenue_metrics(
        session=MagicMock(),
        account_id=uuid.uuid4(),
        account_name="acme",
        start_date=datetime(2026, 5, 1, tzinfo=UTC),
        end_date=datetime(2026, 5, 2, 23, 59, 59, tzinfo=UTC),
        project_ids=[project_id],
    )

    assert result.ordering_enabled is True
    assert result.summary.total_orders == 4
    assert result.summary.palona_revenue == 75.0
    assert result.summary.palona_aov == 25.0
    assert result.payment_path.payment_link.orders == 2
    assert result.payment_path.payment_link.revenue == 50.0
    assert result.payment_path.pay_in_store.orders == 1
    assert result.fulfillment.takeout.orders == 3
    assert result.fulfillment.takeout.share == 75.0
    assert result.fulfillment.delivery.share == 25.0
    assert [point.date for point in result.time_series] == [
        "2026-05-01",
        "2026-05-02",
    ]
    assert result.time_series[0].palona_aov == 25.0
    assert result.time_series[0].payment_link_revenue == 50.0
    assert result.time_series[1].total_orders == 0
    assert result.stores[0].store_id == "store-1"
    assert result.stores[0].store_name == "Downtown"
    assert result.stores[0].project_id == str(project_id)
    assert result.stores[0].palona_aov == 25.0
