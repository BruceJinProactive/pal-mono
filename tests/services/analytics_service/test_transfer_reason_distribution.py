import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from services.analytics_service import _implementation as analytics_impl


class _FakeAnalyticsRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def get_transfer_reason_distribution(
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
                    "tool_failure_order",
                    3,
                    2,
                ),
                (
                    uuid.UUID("11111111-1111-1111-1111-111111111111"),
                    "Acme",
                    "cold_opt_out",
                    1,
                    0,
                ),
            ]

        if group_by == ["date", "project_id"]:
            return [
                (
                    date(2026, 6, 1),
                    uuid.UUID("22222222-2222-2222-2222-222222222222"),
                    "Downtown",
                    "custom_handoff_reason",
                    Decimal("2"),
                    1.0,
                ),
                (
                    "2026-06-01T18:30:00+00:00",
                    uuid.UUID("22222222-2222-2222-2222-222222222222"),
                    "Downtown",
                    "tool_failure_order",
                    "1",
                    None,
                ),
            ]

        return [
            ("tool_failure_order", 3, 2),
            ("cold_opt_out", 1, 0),
        ]


def test_get_transfer_reason_distribution_builds_rows_and_totals(
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

    result = analytics_impl.get_transfer_reason_distribution(
        session=MagicMock(),
        start_date=start_date,
        end_date=end_date,
        group_by=["account_id"],
        filter_by={"account_id": account_id},
    )

    rows = result["transfer_reason_distribution"]
    assert isinstance(rows, list)
    assert rows[0] == {
        "account_id": "11111111-1111-1111-1111-111111111111",
        "account_name": "Acme",
        "reason": "tool_failure_order",
        "transfer_reason_category": "tool_failure_order",
        "label": "Order tool failure",
        "description": "Ordering, checkout, or payment tool failed",
        "count": 3,
        "agent_fault_count": 2,
        "agent_fault_rate": 66.7,
        "percentage": 75.0,
    }
    assert rows[1]["percentage"] == 25.0

    totals = result["totals"]
    assert isinstance(totals, dict)
    assert totals["total_transfer_reason_calls"] == 4
    assert totals["agent_fault_calls"] == 2
    assert totals["agent_fault_rate"] == 50.0
    assert totals["transfer_reason_distribution"] == [
        {
            "reason": "tool_failure_order",
            "transfer_reason_category": "tool_failure_order",
            "label": "Order tool failure",
            "description": "Ordering, checkout, or payment tool failed",
            "count": 3,
            "agent_fault_count": 2,
            "agent_fault_rate": 66.7,
            "percentage": 75.0,
        },
        {
            "reason": "cold_opt_out",
            "transfer_reason_category": "cold_opt_out",
            "label": "Cold opt-out",
            "description": "Generic request to speak with a human",
            "count": 1,
            "agent_fault_count": 0,
            "agent_fault_rate": 0.0,
            "percentage": 25.0,
        },
    ]
    assert result["metadata"] == {
        "group_by": ["account_id"],
        "filter_by": {"account_id": account_id},
    }
    assert [call["group_by"] for call in fake_repo.calls] == [["account_id"], []]


def test_get_transfer_reason_distribution_handles_project_date_groups_and_unknown_reasons(
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

    result = analytics_impl.get_transfer_reason_distribution(
        session=MagicMock(),
        start_date=start_date,
        end_date=end_date,
        group_by=["project_id", "date"],
    )

    assert result["metadata"] == {"group_by": ["date", "project_id"], "filter_by": {}}
    rows = result["transfer_reason_distribution"]
    assert isinstance(rows, list)
    assert rows[0] == {
        "date": "2026-06-01",
        "project_id": "22222222-2222-2222-2222-222222222222",
        "project_name": "Downtown",
        "reason": "custom_handoff_reason",
        "transfer_reason_category": "custom_handoff_reason",
        "label": "Custom Handoff Reason",
        "description": "Custom transfer reason",
        "count": 2,
        "agent_fault_count": 1,
        "agent_fault_rate": 50.0,
        "percentage": 66.7,
    }
    assert rows[1]["agent_fault_count"] == 0
    assert rows[1]["agent_fault_rate"] == 0.0
    assert rows[1]["percentage"] == 33.3
    assert [call["group_by"] for call in fake_repo.calls] == [
        ["date", "project_id"],
        [],
    ]


def test_get_transfer_reason_distribution_defaults_to_empty_grouping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class EmptyAnalyticsRepository:
        def __init__(self, session: object) -> None:
            self.calls: list[list[str] | None] = []

        def get_transfer_reason_distribution(
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

    result = analytics_impl.get_transfer_reason_distribution(
        session=MagicMock(),
        start_date=datetime(2026, 6, 1, tzinfo=timezone.utc),
        end_date=datetime(2026, 6, 16, tzinfo=timezone.utc),
        group_by=None,
        filter_by=None,
    )

    assert result == {
        "transfer_reason_distribution": [],
        "totals": {
            "total_transfer_reason_calls": 0,
            "agent_fault_calls": 0,
            "agent_fault_rate": None,
            "transfer_reason_distribution": [],
        },
        "metadata": {"group_by": [], "filter_by": {}},
    }
    assert empty_repo.calls == [[]]


def test_get_transfer_reason_distribution_reraises_repository_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RaisingAnalyticsRepository:
        def __init__(self, session: object) -> None:
            pass

        def get_transfer_reason_distribution(
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
        analytics_impl.get_transfer_reason_distribution(
            session=MagicMock(),
            start_date=datetime(2026, 6, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 6, 16, tzinfo=timezone.utc),
            group_by=["account_id"],
        )
