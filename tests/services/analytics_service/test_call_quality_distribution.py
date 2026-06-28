import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from db.tables.types import CallQualityLabel
from services.analytics_service import _implementation as analytics_impl


class _FakeAnalyticsRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def get_call_quality_distribution(
        self,
        start_date: datetime,
        end_date: datetime,
        group_by: list[str] | None = None,
        filter_by: dict[str, uuid.UUID | list[uuid.UUID]] | None = None,
    ) -> list[tuple[object, ...]]:
        self.calls.append(
            {
                "start_date": start_date,
                "end_date": end_date,
                "group_by": group_by,
                "filter_by": filter_by,
            }
        )

        if group_by == ["account_id"]:
            return [
                (
                    uuid.UUID("11111111-1111-1111-1111-111111111111"),
                    "Acme",
                    CallQualityLabel.legitimate_restaurant_call,
                    6,
                ),
                (
                    uuid.UUID("11111111-1111-1111-1111-111111111111"),
                    "Acme",
                    CallQualityLabel.promotional_sales,
                    3,
                ),
                (
                    uuid.UUID("11111111-1111-1111-1111-111111111111"),
                    "Acme",
                    CallQualityLabel.spam_scam,
                    1,
                ),
            ]

        if group_by == ["date", "project_id"]:
            return [
                (
                    date(2026, 6, 1),
                    uuid.UUID("22222222-2222-2222-2222-222222222222"),
                    "Downtown",
                    "custom_quality_label",
                    Decimal("2"),
                ),
                (
                    "2026-06-01T18:30:00+00:00",
                    uuid.UUID("22222222-2222-2222-2222-222222222222"),
                    "Downtown",
                    CallQualityLabel.robot_prerecorded,
                    "1",
                ),
            ]

        return [
            (CallQualityLabel.legitimate_restaurant_call, 10),
            (CallQualityLabel.promotional_sales, 3),
            (CallQualityLabel.unknown_unclear, 1),
        ]


def test_get_call_quality_distribution_builds_rows_and_totals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_repo = _FakeAnalyticsRepository()

    def fake_repository(session: object) -> _FakeAnalyticsRepository:
        return fake_repo

    monkeypatch.setattr(
        analytics_impl.db,
        "AnalyticsRepository",
        fake_repository,
    )
    start_date = datetime(2026, 6, 1, tzinfo=timezone.utc)
    end_date = datetime(2026, 6, 16, tzinfo=timezone.utc)
    account_id = uuid.uuid4()

    result = analytics_impl.get_call_quality_distribution(
        session=MagicMock(),
        start_date=start_date,
        end_date=end_date,
        group_by=["account_id"],
        filter_by={"account_id": account_id},
    )

    rows = result["call_quality_distribution"]
    assert isinstance(rows, list)
    assert rows[0] == {
        "account_id": "11111111-1111-1111-1111-111111111111",
        "account_name": "Acme",
        "call_quality_label": "legitimate_restaurant_call",
        "label": "Legit calls",
        "description": "Real restaurant or customer-service intent",
        "count": 6,
        "is_legitimate": True,
        "percentage": 60.0,
    }
    assert rows[1]["call_quality_label"] == "promotional_sales"
    assert rows[1]["percentage"] == 30.0
    assert rows[2]["percentage"] == 10.0

    totals = result["totals"]
    assert isinstance(totals, dict)
    assert totals["total_call_quality_calls"] == 14
    assert totals["total_legitimate_calls"] == 10
    assert totals["total_non_legitimate_calls"] == 4
    assert totals["legitimate_rate"] == 71.4
    assert totals["non_legitimate_rate"] == 28.6
    assert totals["call_quality_distribution"] == [
        {
            "call_quality_label": "legitimate_restaurant_call",
            "label": "Legit calls",
            "description": "Real restaurant or customer-service intent",
            "count": 10,
            "is_legitimate": True,
            "percentage": 71.4,
        },
        {
            "call_quality_label": "promotional_sales",
            "label": "Promotional sales",
            "description": "Vendor, marketing, supplier, recruiting, or sales outreach",
            "count": 3,
            "is_legitimate": False,
            "percentage": 21.4,
        },
        {
            "call_quality_label": "unknown_unclear",
            "label": "Unknown / unclear",
            "description": "Silence, no usable caller speech, or insufficient evidence",
            "count": 1,
            "is_legitimate": False,
            "percentage": 7.1,
        },
    ]
    assert result["metadata"] == {
        "group_by": ["account_id"],
        "filter_by": {"account_id": account_id},
    }
    assert [call["group_by"] for call in fake_repo.calls] == [["account_id"], []]


def test_get_call_quality_distribution_handles_project_date_groups_and_unknown_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_repo = _FakeAnalyticsRepository()

    def fake_repository(session: object) -> _FakeAnalyticsRepository:
        return fake_repo

    monkeypatch.setattr(
        analytics_impl.db,
        "AnalyticsRepository",
        fake_repository,
    )

    result = analytics_impl.get_call_quality_distribution(
        session=MagicMock(),
        start_date=datetime(2026, 6, 1, tzinfo=timezone.utc),
        end_date=datetime(2026, 6, 16, tzinfo=timezone.utc),
        group_by=["project_id", "date"],
    )

    assert result["metadata"] == {"group_by": ["date", "project_id"], "filter_by": {}}
    rows = result["call_quality_distribution"]
    assert isinstance(rows, list)
    assert rows[0] == {
        "date": "2026-06-01",
        "project_id": "22222222-2222-2222-2222-222222222222",
        "project_name": "Downtown",
        "call_quality_label": "custom_quality_label",
        "label": "Custom Quality Label",
        "description": "Custom call quality label",
        "count": 2,
        "is_legitimate": False,
        "percentage": 66.7,
    }
    assert rows[1]["call_quality_label"] == "robot_prerecorded"
    assert rows[1]["percentage"] == 33.3
    assert [call["group_by"] for call in fake_repo.calls] == [
        ["date", "project_id"],
        [],
    ]


def test_get_call_quality_distribution_populates_rows_without_grouping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_repo = _FakeAnalyticsRepository()

    def fake_repository(session: object) -> _FakeAnalyticsRepository:
        return fake_repo

    monkeypatch.setattr(
        analytics_impl.db,
        "AnalyticsRepository",
        fake_repository,
    )

    result = analytics_impl.get_call_quality_distribution(
        session=MagicMock(),
        start_date=datetime(2026, 6, 1, tzinfo=timezone.utc),
        end_date=datetime(2026, 6, 16, tzinfo=timezone.utc),
        group_by=None,
    )

    rows = result["call_quality_distribution"]
    totals = result["totals"]
    assert isinstance(rows, list)
    assert isinstance(totals, dict)
    assert rows == totals["call_quality_distribution"]
    assert rows == [
        {
            "call_quality_label": "legitimate_restaurant_call",
            "label": "Legit calls",
            "description": "Real restaurant or customer-service intent",
            "count": 10,
            "is_legitimate": True,
            "percentage": 71.4,
        },
        {
            "call_quality_label": "promotional_sales",
            "label": "Promotional sales",
            "description": "Vendor, marketing, supplier, recruiting, or sales outreach",
            "count": 3,
            "is_legitimate": False,
            "percentage": 21.4,
        },
        {
            "call_quality_label": "unknown_unclear",
            "label": "Unknown / unclear",
            "description": "Silence, no usable caller speech, or insufficient evidence",
            "count": 1,
            "is_legitimate": False,
            "percentage": 7.1,
        },
    ]
    assert totals["total_call_quality_calls"] == 14
    assert [call["group_by"] for call in fake_repo.calls] == [[]]


def test_get_call_quality_distribution_defaults_to_empty_grouping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class EmptyAnalyticsRepository:
        def __init__(self, session: object) -> None:
            self.calls: list[list[str] | None] = []

        def get_call_quality_distribution(
            self,
            start_date: datetime,
            end_date: datetime,
            group_by: list[str] | None = None,
            filter_by: dict[str, uuid.UUID | list[uuid.UUID]] | None = None,
        ) -> list[tuple[object, ...]]:
            self.calls.append(group_by)
            return []

    empty_repo = EmptyAnalyticsRepository(session=MagicMock())

    def fake_repository(session: object) -> EmptyAnalyticsRepository:
        return empty_repo

    monkeypatch.setattr(
        analytics_impl.db,
        "AnalyticsRepository",
        fake_repository,
    )

    result = analytics_impl.get_call_quality_distribution(
        session=MagicMock(),
        start_date=datetime(2026, 6, 1, tzinfo=timezone.utc),
        end_date=datetime(2026, 6, 16, tzinfo=timezone.utc),
        group_by=None,
        filter_by=None,
    )

    assert result == {
        "call_quality_distribution": [],
        "totals": {
            "total_call_quality_calls": 0,
            "total_legitimate_calls": 0,
            "total_non_legitimate_calls": 0,
            "legitimate_rate": None,
            "non_legitimate_rate": None,
            "call_quality_distribution": [],
        },
        "metadata": {"group_by": [], "filter_by": {}},
    }
    assert empty_repo.calls == [[]]


def test_get_call_quality_distribution_reraises_repository_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RaisingAnalyticsRepository:
        def __init__(self, session: object) -> None:
            pass

        def get_call_quality_distribution(
            self,
            start_date: datetime,
            end_date: datetime,
            group_by: list[str] | None = None,
            filter_by: dict[str, uuid.UUID | list[uuid.UUID]] | None = None,
        ) -> list[tuple[object, ...]]:
            raise RuntimeError("repository unavailable")

    def fake_repository(session: object) -> RaisingAnalyticsRepository:
        return RaisingAnalyticsRepository(session)

    monkeypatch.setattr(
        analytics_impl.db,
        "AnalyticsRepository",
        fake_repository,
    )

    with pytest.raises(RuntimeError, match="repository unavailable"):
        analytics_impl.get_call_quality_distribution(
            session=MagicMock(),
            start_date=datetime(2026, 6, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 6, 16, tzinfo=timezone.utc),
            group_by=["account_id"],
        )
