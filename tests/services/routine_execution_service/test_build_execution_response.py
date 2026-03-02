"""Tests for _build_execution_response missed status detection."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from db.tables.types import ExecutionStatus, RoutineCategory
from services.routine_execution_service._implementation import _build_execution_response


def _make_execution(**overrides) -> MagicMock:
    execution = MagicMock()
    execution.id = overrides.get("id", uuid.uuid4())
    execution.routine_id = overrides.get("routine_id", uuid.uuid4())
    execution.schedule_id = overrides.get("schedule_id", uuid.uuid4())
    execution.scheduled_start = overrides.get(
        "scheduled_start", datetime(2026, 3, 2, 14, 0, tzinfo=timezone.utc)
    )
    execution.scheduled_end = overrides.get(
        "scheduled_end", datetime(2026, 3, 2, 15, 0, tzinfo=timezone.utc)
    )
    execution.status = overrides.get("status", ExecutionStatus.pending)
    execution.assigned_user_id = overrides.get("assigned_user_id", None)
    execution.created_at = overrides.get(
        "created_at", datetime(2026, 3, 2, 0, 0, tzinfo=timezone.utc)
    )
    execution.updated_at = overrides.get(
        "updated_at", datetime(2026, 3, 2, 0, 0, tzinfo=timezone.utc)
    )
    return execution


_COMMON_KWARGS = {
    "routine_name": "Opening",
    "routine_category": RoutineCategory.opening,
    "routine_item_count": 3,
    "submission_id": None,
    "submission_status": None,
    "submission_completed_count": 0,
}


class TestBuildExecutionResponseMissedStatus:
    """Cover missed status auto-detection in _build_execution_response."""

    def test_pending_past_scheduled_end_becomes_missed(self) -> None:
        """Pending execution past its scheduled_end should be marked missed."""
        now = datetime.now(timezone.utc)
        execution = _make_execution(
            status=ExecutionStatus.pending,
            scheduled_end=now - timedelta(hours=1),
        )

        result = _build_execution_response(
            execution=execution, **_COMMON_KWARGS, now_utc=now
        )

        assert result.status == ExecutionStatus.missed

    def test_pending_before_scheduled_end_stays_pending(self) -> None:
        """Pending execution before its scheduled_end should stay pending."""
        now = datetime.now(timezone.utc)
        execution = _make_execution(
            status=ExecutionStatus.pending,
            scheduled_end=now + timedelta(hours=1),
        )

        result = _build_execution_response(
            execution=execution, **_COMMON_KWARGS, now_utc=now
        )

        assert result.status == ExecutionStatus.pending

    def test_completed_past_scheduled_end_stays_completed(self) -> None:
        """Non-pending execution should not be changed to missed."""
        now = datetime.now(timezone.utc)
        execution = _make_execution(
            status=ExecutionStatus.completed,
            scheduled_end=now - timedelta(hours=1),
        )

        result = _build_execution_response(
            execution=execution, **_COMMON_KWARGS, now_utc=now
        )

        assert result.status == ExecutionStatus.completed

    def test_pending_exactly_at_scheduled_end_stays_pending(self) -> None:
        """Boundary: scheduled_end == now_utc uses strict '<', so stays pending."""
        now = datetime.now(timezone.utc)
        execution = _make_execution(
            status=ExecutionStatus.pending,
            scheduled_end=now,
        )

        result = _build_execution_response(
            execution=execution, **_COMMON_KWARGS, now_utc=now
        )

        assert result.status == ExecutionStatus.pending

    def test_now_utc_defaults_when_not_provided(self) -> None:
        """When now_utc is omitted, datetime.now(utc) is used automatically."""
        execution = _make_execution(
            status=ExecutionStatus.pending,
            scheduled_end=datetime.now(timezone.utc) - timedelta(hours=1),
        )

        result = _build_execution_response(execution=execution, **_COMMON_KWARGS)

        assert result.status == ExecutionStatus.missed
