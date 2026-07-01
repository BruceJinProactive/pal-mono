import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from db.tables.types import CallEndedReason
from services import analytics_service
from services.analytics_service import _implementation as analytics_impl


class _FakeAnalyticsRepository:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.rows = rows
        self.calls: list[dict[str, object]] = []

    def get_call_insights(
        self,
        start_date: datetime,
        end_date: datetime,
        filter_by: dict[str, uuid.UUID | list[uuid.UUID]] | None = None,
    ) -> list[tuple[object, ...]]:
        self.calls.append(
            {
                "start_date": start_date,
                "end_date": end_date,
                "filter_by": filter_by,
            }
        )
        return self.rows


def _row(
    *,
    call_id: str,
    conversation_id: uuid.UUID,
    started_at: datetime,
    duration: float | None,
    is_test: bool = False,
    transfer_purpose: str | None = None,
    transfer_reason_category: str | None = None,
    transfer_requested_at: datetime | None = None,
    transfer_destination: str | None = None,
    prior_call_count: int = 0,
    project_id: uuid.UUID | None = None,
    business_hours: dict | None = None,
    store_hours: str | None = None,
    ended_reason: object | None = None,
) -> tuple[object, ...]:
    account_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    return (
        call_id,
        conversation_id,
        started_at,
        duration,
        (
            ended_reason
            if ended_reason is not None
            else "assistant_forwarded" if transfer_purpose else "customer_ended"
        ),
        transfer_reason_category,
        is_test,
        transfer_purpose,
        uuid.uuid4(),
        ["+15551234567"],
        account_id,
        "acme",
        project_id,
        "Downtown" if project_id else None,
        "America/Los_Angeles",
        business_hours,
        store_hours,
        transfer_destination,
        transfer_requested_at,
        prior_call_count,
    )


def test_get_call_insights_builds_requested_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    conv_a = uuid.UUID("11111111-1111-1111-1111-111111111111")
    conv_b = uuid.UUID("22222222-2222-2222-2222-222222222222")
    start = datetime(2026, 6, 1, tzinfo=UTC)
    end = datetime(2026, 6, 2, tzinfo=UTC)
    rows = [
        _row(
            call_id="call-a",
            conversation_id=conv_a,
            started_at=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
            duration=120,
            transfer_reason_category="tool_failure_order",
            transfer_requested_at=datetime(2026, 6, 1, 10, 1, tzinfo=UTC),
            transfer_destination="+15550001111",
            project_id=project_id,
            store_hours="Monday: 9:00 AM - 5:00 PM",
            ended_reason=CallEndedReason.assistant_forwarded,
        ),
        _row(
            call_id="call-b",
            conversation_id=conv_b,
            started_at=datetime(2026, 6, 1, 10, 1, tzinfo=UTC),
            duration=30,
            is_test=True,
            prior_call_count=2,
            project_id=project_id,
            store_hours="Monday: 9:00 AM - 5:00 PM",
            transfer_destination="+15550009999",
        ),
    ]
    fake_repo = _FakeAnalyticsRepository(rows)

    monkeypatch.setattr(
        analytics_impl.db,
        "AnalyticsRepository",
        lambda session: fake_repo,
    )

    result = analytics_impl.get_call_insights(
        session=MagicMock(),
        account_id=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        start_date=start,
        end_date=end,
        project_ids=[project_id],
    )

    assert fake_repo.calls[0]["filter_by"] == {
        "account_id": uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        "project_id": [project_id],
    }
    assert result.summary.total_calls == 2
    assert result.summary.avg_duration_seconds == 75.0
    assert result.summary.internal_test_calls == 1
    assert result.summary.new_callers == 1
    assert result.summary.repeat_callers == 1
    assert result.summary.transfer_requested_calls == 1
    assert result.summary.concurrent_calls == 2
    assert result.summary.spam_calls is None
    assert result.summary.transfer_answered_calls is None
    assert result.period_start == start
    assert result.period_end == end
    assert result.metric_availability["spam_calls"].available is False
    assert result.metric_availability["transferred_call_answered"].available is False

    first = result.calls[0]
    assert first.call_id == "call-a"
    assert first.duration_seconds == 120.0
    assert first.transfer_requested is True
    assert first.transfer_destination == "+15550001111"
    assert first.transfer_reason == "tool_failure_order"
    assert first.transfer_requested_at == datetime(2026, 6, 1, 10, 1, tzinfo=UTC)
    assert first.has_concurrent_call is True
    assert first.is_spam is None

    second = result.calls[1]
    assert second.transfer_requested is False
    assert second.transfer_destination is None
    assert second.transfer_reason is None
    assert second.transfer_requested_at is None


def test_get_call_insights_after_hours_null_when_hours_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        _row(
            call_id="call-a",
            conversation_id=uuid.uuid4(),
            started_at=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
            duration=None,
        )
    ]
    monkeypatch.setattr(
        analytics_impl.db,
        "AnalyticsRepository",
        lambda session: _FakeAnalyticsRepository(rows),
    )

    result = analytics_impl.get_call_insights(
        session=MagicMock(),
        account_id=uuid.uuid4(),
        start_date=datetime(2026, 6, 1, tzinfo=UTC),
        end_date=datetime(2026, 6, 2, tzinfo=UTC),
    )

    assert result.summary.avg_duration_seconds is None
    assert result.summary.after_hours_calls is None
    assert result.calls[0].is_after_hours is None


def test_get_call_insights_does_not_mark_unknown_project_calls_concurrent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        _row(
            call_id="call-a",
            conversation_id=uuid.uuid4(),
            started_at=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
            duration=120,
        ),
        _row(
            call_id="call-b",
            conversation_id=uuid.uuid4(),
            started_at=datetime(2026, 6, 1, 10, 1, tzinfo=UTC),
            duration=30,
        ),
    ]
    monkeypatch.setattr(
        analytics_impl.db,
        "AnalyticsRepository",
        lambda session: _FakeAnalyticsRepository(rows),
    )

    result = analytics_impl.get_call_insights(
        session=MagicMock(),
        account_id=uuid.uuid4(),
        start_date=datetime(2026, 6, 1, tzinfo=UTC),
        end_date=datetime(2026, 6, 2, tzinfo=UTC),
    )

    assert result.summary.concurrent_calls == 0
    assert [record.has_concurrent_call for record in result.calls] == [False, False]


def test_public_get_call_insights_delegates_to_implementation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = object()
    mock_get_call_insights = MagicMock(return_value=response)
    monkeypatch.setattr(
        analytics_service._implementation,
        "get_call_insights",
        mock_get_call_insights,
    )
    session = MagicMock()
    account_id = uuid.uuid4()
    project_id = uuid.uuid4()
    start = datetime(2026, 6, 1, tzinfo=UTC)
    end = datetime(2026, 6, 2, tzinfo=UTC)

    result = analytics_service.get_call_insights(
        session=session,
        account_id=account_id,
        start_date=start,
        end_date=end,
        project_ids=[project_id],
    )

    assert result is response
    mock_get_call_insights.assert_called_once_with(
        session=session,
        account_id=account_id,
        start_date=start,
        end_date=end,
        project_ids=[project_id],
    )


def test_as_utc_marks_naive_datetimes_as_utc() -> None:
    naive = datetime(2026, 6, 1, 10, 0)

    assert analytics_impl._as_utc(naive) == datetime(2026, 6, 1, 10, 0, tzinfo=UTC)


def test_has_concurrent_call_returns_false_for_non_overlapping_known_project() -> None:
    project_id = uuid.uuid4()
    windows = [
        (
            project_id,
            datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
            datetime(2026, 6, 1, 10, 1, tzinfo=UTC),
        ),
        (
            project_id,
            datetime(2026, 6, 1, 10, 2, tzinfo=UTC),
            datetime(2026, 6, 1, 10, 3, tzinfo=UTC),
        ),
    ]

    assert analytics_impl._has_concurrent_call(0, windows) is False
