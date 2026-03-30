import sys
import uuid
from datetime import date, datetime, time, timedelta, timezone
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import sqlalchemy.engine
import sqlalchemy.ext.asyncio
import sqlalchemy.orm


class _TraceSpan:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def set_tag(self, key, value):
        return None


class _TracerStub:
    def current_span(self):
        return None

    def trace(self, *args, **kwargs):
        return _TraceSpan()


class _LLMObsStub:
    @staticmethod
    def annotate(**kwargs):
        return None


class _DogStatsdStub:
    def __init__(self, *args, **kwargs):
        pass

    def histogram(self, *args, **kwargs):
        return None


ddtrace_stub = ModuleType("ddtrace")
setattr(ddtrace_stub, "tracer", _TracerStub())
sys.modules.setdefault("ddtrace", ddtrace_stub)

ddtrace_llmobs_stub = ModuleType("ddtrace.llmobs")
setattr(ddtrace_llmobs_stub, "LLMObs", _LLMObsStub)
sys.modules.setdefault("ddtrace.llmobs", ddtrace_llmobs_stub)

datadog_stub = ModuleType("datadog")
setattr(datadog_stub, "DogStatsd", _DogStatsdStub)
sys.modules.setdefault("datadog", datadog_stub)

boto3_stub = ModuleType("boto3")
setattr(boto3_stub, "client", lambda *args, **kwargs: object())
sys.modules.setdefault("boto3", boto3_stub)

botocore_exceptions_stub = ModuleType("botocore.exceptions")
setattr(botocore_exceptions_stub, "ClientError", Exception)
sys.modules.setdefault("botocore.exceptions", botocore_exceptions_stub)

sqlalchemy.engine.create_engine = lambda *args, **kwargs: object()
sqlalchemy.ext.asyncio.create_async_engine = lambda *args, **kwargs: object()
sqlalchemy.orm.sessionmaker = lambda *args, **kwargs: lambda *a, **kw: None
sqlalchemy.ext.asyncio.async_sessionmaker = (
    lambda *args, **kwargs: lambda *a, **kw: None
)

from api.schemas.catering.catering import Contact as ContactSchema  # noqa: E402
from db.tables.catering_requests import CateringRequest, RequestStatus  # noqa: E402
from services.catering_service._implementation import (  # noqa: E402
    format_catering_apology_message,
    format_catering_reminder_message,
    send_catering_inquiry_apologies,
    send_catering_inquiry_reminders,
)

# Fixed "now" for deterministic tests: 2026-03-24 19:00 UTC
NOW_UTC = datetime(2026, 3, 24, 19, 0, 0, tzinfo=timezone.utc)
TWO_DAYS_AGO_UTC = NOW_UTC - timedelta(days=2)

PROJECT_ID = uuid.uuid4()
PROJECT_ID_2 = uuid.uuid4()


def _make_request(
    *,
    project_id: uuid.UUID = PROJECT_ID,
    created_at: datetime = TWO_DAYS_AGO_UTC,
    event_date: date = date(2026, 3, 28),
    event_time: time | None = None,
    status: RequestStatus = RequestStatus.INQUIRY,
) -> CateringRequest:
    return CateringRequest(
        id=uuid.uuid4(),
        project_id=project_id,
        event_date=event_date,
        event_time=event_time,
        contact_name="Taylor",
        contact_phone_number="5551234567",
        party_size=25,
        status=status,
        idempotency_key=str(uuid.uuid4()),
        created_at=created_at,
    )


def _make_project(
    project_id: uuid.UUID = PROJECT_ID,
    timezone: str = "America/Chicago",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=project_id,
        timezone=timezone,
        account=SimpleNamespace(display_name="Pal Bistro", name="pal-bistro"),
        name="pal-bistro-downtown",
        display_name="Pal Bistro Downtown",
    )


def _make_contact() -> ContactSchema:
    return ContactSchema(
        id=uuid.uuid4(),
        name="Manager Mike",
        phone_number="5559876543",
        role="catering_manager",
        email=None,
        created_at=NOW_UTC,
        updated_at=NOW_UTC,
    )


SERVICE_MODULE = "services.catering_service._implementation"


@pytest.mark.asyncio
async def test_happy_path_sends_reminder() -> None:
    """2-day-old INQUIRY request with future event -> sends SMS."""
    session = AsyncMock()
    req = _make_request()
    project = _make_project()
    contact = _make_contact()

    catering_repo = AsyncMock()
    catering_repo.list_inquiry_requests_in_date_range.return_value = [req]
    project_repo = AsyncMock()
    project_repo.list_projects_by_ids.return_value = [project]

    with (
        patch(f"{SERVICE_MODULE}.datetime") as mock_dt,
        patch(
            f"{SERVICE_MODULE}.CateringRequestRepositoryAsync",
            return_value=catering_repo,
        ),
        patch(
            f"{SERVICE_MODULE}.ProjectRepositoryAsync",
            return_value=project_repo,
        ),
        patch(
            f"{SERVICE_MODULE}._find_catering_manager_for_project",
            return_value=contact,
        ),
        patch(
            f"{SERVICE_MODULE}.send_sms_notification",
            return_value=True,
        ) as mock_sms,
    ):
        mock_dt.now.return_value = NOW_UTC
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = await send_catering_inquiry_reminders(session)

    assert result.reminders_sent == 1
    assert result.success is True
    mock_sms.assert_called_once()
    msg = mock_sms.call_args[0][1]
    assert "2 days ago" in msg.lower()


@pytest.mark.asyncio
async def test_no_candidates_returns_empty() -> None:
    """No INQUIRY requests in date range -> no SMS sent."""
    session = AsyncMock()
    catering_repo = AsyncMock()
    catering_repo.list_inquiry_requests_in_date_range.return_value = []

    with (
        patch(f"{SERVICE_MODULE}.datetime") as mock_dt,
        patch(
            f"{SERVICE_MODULE}.CateringRequestRepositoryAsync",
            return_value=catering_repo,
        ),
    ):
        mock_dt.now.return_value = NOW_UTC
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = await send_catering_inquiry_reminders(session)

    assert result.reminders_sent == 0
    assert result.projects_checked == 0


@pytest.mark.asyncio
async def test_request_1_day_old_excluded() -> None:
    """Request created 1 day ago should not trigger a reminder."""
    session = AsyncMock()
    req = _make_request(created_at=NOW_UTC - timedelta(days=1))
    project = _make_project()

    catering_repo = AsyncMock()
    catering_repo.list_inquiry_requests_in_date_range.return_value = [req]
    project_repo = AsyncMock()
    project_repo.list_projects_by_ids.return_value = [project]

    with (
        patch(f"{SERVICE_MODULE}.datetime") as mock_dt,
        patch(
            f"{SERVICE_MODULE}.CateringRequestRepositoryAsync",
            return_value=catering_repo,
        ),
        patch(
            f"{SERVICE_MODULE}.ProjectRepositoryAsync",
            return_value=project_repo,
        ),
        patch(
            f"{SERVICE_MODULE}._find_catering_manager_for_project",
        ),
        patch(f"{SERVICE_MODULE}.send_sms_notification") as mock_sms,
    ):
        mock_dt.now.return_value = NOW_UTC
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = await send_catering_inquiry_reminders(session)

    assert result.reminders_sent == 0
    mock_sms.assert_not_called()


@pytest.mark.asyncio
async def test_request_3_days_old_excluded() -> None:
    """Request created 3 days ago should not trigger a reminder."""
    session = AsyncMock()
    req = _make_request(created_at=NOW_UTC - timedelta(days=3))
    project = _make_project()

    catering_repo = AsyncMock()
    catering_repo.list_inquiry_requests_in_date_range.return_value = [req]
    project_repo = AsyncMock()
    project_repo.list_projects_by_ids.return_value = [project]

    with (
        patch(f"{SERVICE_MODULE}.datetime") as mock_dt,
        patch(
            f"{SERVICE_MODULE}.CateringRequestRepositoryAsync",
            return_value=catering_repo,
        ),
        patch(
            f"{SERVICE_MODULE}.ProjectRepositoryAsync",
            return_value=project_repo,
        ),
        patch(f"{SERVICE_MODULE}._find_catering_manager_for_project"),
        patch(f"{SERVICE_MODULE}.send_sms_notification") as mock_sms,
    ):
        mock_dt.now.return_value = NOW_UTC
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = await send_catering_inquiry_reminders(session)

    assert result.reminders_sent == 0
    mock_sms.assert_not_called()


@pytest.mark.asyncio
async def test_event_date_passed_excluded() -> None:
    """Request with event_date in the past should be excluded."""
    session = AsyncMock()
    req = _make_request(event_date=date(2026, 3, 20))  # in the past
    project = _make_project()

    catering_repo = AsyncMock()
    catering_repo.list_inquiry_requests_in_date_range.return_value = [req]
    project_repo = AsyncMock()
    project_repo.list_projects_by_ids.return_value = [project]

    with (
        patch(f"{SERVICE_MODULE}.datetime") as mock_dt,
        patch(
            f"{SERVICE_MODULE}.CateringRequestRepositoryAsync",
            return_value=catering_repo,
        ),
        patch(
            f"{SERVICE_MODULE}.ProjectRepositoryAsync",
            return_value=project_repo,
        ),
        patch(f"{SERVICE_MODULE}._find_catering_manager_for_project"),
        patch(f"{SERVICE_MODULE}.send_sms_notification") as mock_sms,
    ):
        mock_dt.now.return_value = NOW_UTC
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = await send_catering_inquiry_reminders(session)

    assert result.reminders_sent == 0
    mock_sms.assert_not_called()


@pytest.mark.asyncio
async def test_event_time_passed_today_excluded() -> None:
    """Request with event today and event_time already passed should be excluded."""
    session = AsyncMock()
    # Event is today at 10:00 AM, but current time is 2 PM Central (19:00 UTC)
    req = _make_request(
        event_date=date(2026, 3, 24),
        event_time=time(10, 0),
    )
    project = _make_project(timezone="America/Chicago")

    catering_repo = AsyncMock()
    catering_repo.list_inquiry_requests_in_date_range.return_value = [req]
    project_repo = AsyncMock()
    project_repo.list_projects_by_ids.return_value = [project]

    with (
        patch(f"{SERVICE_MODULE}.datetime") as mock_dt,
        patch(
            f"{SERVICE_MODULE}.CateringRequestRepositoryAsync",
            return_value=catering_repo,
        ),
        patch(
            f"{SERVICE_MODULE}.ProjectRepositoryAsync",
            return_value=project_repo,
        ),
        patch(f"{SERVICE_MODULE}._find_catering_manager_for_project"),
        patch(f"{SERVICE_MODULE}.send_sms_notification") as mock_sms,
    ):
        mock_dt.now.return_value = NOW_UTC
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = await send_catering_inquiry_reminders(session)

    assert result.reminders_sent == 0
    mock_sms.assert_not_called()


@pytest.mark.asyncio
async def test_multiple_requests_same_project_one_sms() -> None:
    """Multiple qualifying requests for one project -> one SMS."""
    session = AsyncMock()
    req1 = _make_request()
    req2 = _make_request()
    project = _make_project()
    contact = _make_contact()

    catering_repo = AsyncMock()
    catering_repo.list_inquiry_requests_in_date_range.return_value = [req1, req2]
    project_repo = AsyncMock()
    project_repo.list_projects_by_ids.return_value = [project]

    with (
        patch(f"{SERVICE_MODULE}.datetime") as mock_dt,
        patch(
            f"{SERVICE_MODULE}.CateringRequestRepositoryAsync",
            return_value=catering_repo,
        ),
        patch(
            f"{SERVICE_MODULE}.ProjectRepositoryAsync",
            return_value=project_repo,
        ),
        patch(
            f"{SERVICE_MODULE}._find_catering_manager_for_project",
            return_value=contact,
        ),
        patch(
            f"{SERVICE_MODULE}.send_sms_notification",
            return_value=True,
        ) as mock_sms,
    ):
        mock_dt.now.return_value = NOW_UTC
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = await send_catering_inquiry_reminders(session)

    assert result.reminders_sent == 1
    mock_sms.assert_called_once()
    msg = mock_sms.call_args[0][1]
    assert "2 days ago" in msg.lower()


@pytest.mark.asyncio
async def test_multiple_projects_separate_sms() -> None:
    """Qualifying requests across two projects -> two SMS messages."""
    session = AsyncMock()
    req1 = _make_request(project_id=PROJECT_ID)
    req2 = _make_request(project_id=PROJECT_ID_2)
    project1 = _make_project(project_id=PROJECT_ID)
    project2 = _make_project(project_id=PROJECT_ID_2)
    contact = _make_contact()

    catering_repo = AsyncMock()
    catering_repo.list_inquiry_requests_in_date_range.return_value = [req1, req2]
    project_repo = AsyncMock()
    project_repo.list_projects_by_ids.return_value = [project1, project2]

    with (
        patch(f"{SERVICE_MODULE}.datetime") as mock_dt,
        patch(
            f"{SERVICE_MODULE}.CateringRequestRepositoryAsync",
            return_value=catering_repo,
        ),
        patch(
            f"{SERVICE_MODULE}.ProjectRepositoryAsync",
            return_value=project_repo,
        ),
        patch(
            f"{SERVICE_MODULE}._find_catering_manager_for_project",
            return_value=contact,
        ),
        patch(
            f"{SERVICE_MODULE}.send_sms_notification",
            return_value=True,
        ) as mock_sms,
    ):
        mock_dt.now.return_value = NOW_UTC
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = await send_catering_inquiry_reminders(session)

    assert result.reminders_sent == 2
    assert mock_sms.call_count == 2


@pytest.mark.asyncio
async def test_no_catering_manager_skipped() -> None:
    """Project without catering manager -> skipped, no crash."""
    session = AsyncMock()
    req = _make_request()
    project = _make_project()

    catering_repo = AsyncMock()
    catering_repo.list_inquiry_requests_in_date_range.return_value = [req]
    project_repo = AsyncMock()
    project_repo.list_projects_by_ids.return_value = [project]

    with (
        patch(f"{SERVICE_MODULE}.datetime") as mock_dt,
        patch(
            f"{SERVICE_MODULE}.CateringRequestRepositoryAsync",
            return_value=catering_repo,
        ),
        patch(
            f"{SERVICE_MODULE}.ProjectRepositoryAsync",
            return_value=project_repo,
        ),
        patch(
            f"{SERVICE_MODULE}._find_catering_manager_for_project",
            return_value=None,
        ),
        patch(f"{SERVICE_MODULE}.send_sms_notification") as mock_sms,
    ):
        mock_dt.now.return_value = NOW_UTC
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = await send_catering_inquiry_reminders(session)

    assert result.reminders_sent == 0
    assert result.success is True
    mock_sms.assert_not_called()


@pytest.mark.asyncio
async def test_different_timezones_correct_filtering() -> None:
    """Requests are filtered based on the project's timezone, not UTC."""
    session = AsyncMock()
    # At 19:00 UTC on Mar 24:
    #   - In ET (UTC-4): it's 15:00 on Mar 24, so 2 days ago = Mar 22
    #   - In PT (UTC-7): it's 12:00 on Mar 24, so 2 days ago = Mar 22
    # Request created Mar 22 12:00 UTC -> Mar 22 in both ET and PT
    req_et = _make_request(
        project_id=PROJECT_ID,
        created_at=datetime(2026, 3, 22, 12, 0, 0, tzinfo=timezone.utc),
    )
    req_pt = _make_request(
        project_id=PROJECT_ID_2,
        created_at=datetime(2026, 3, 22, 12, 0, 0, tzinfo=timezone.utc),
    )
    project_et = _make_project(project_id=PROJECT_ID, timezone="America/New_York")
    project_pt = _make_project(project_id=PROJECT_ID_2, timezone="America/Los_Angeles")
    contact = _make_contact()

    catering_repo = AsyncMock()
    catering_repo.list_inquiry_requests_in_date_range.return_value = [req_et, req_pt]
    project_repo = AsyncMock()
    project_repo.list_projects_by_ids.return_value = [project_et, project_pt]

    with (
        patch(f"{SERVICE_MODULE}.datetime") as mock_dt,
        patch(
            f"{SERVICE_MODULE}.CateringRequestRepositoryAsync",
            return_value=catering_repo,
        ),
        patch(
            f"{SERVICE_MODULE}.ProjectRepositoryAsync",
            return_value=project_repo,
        ),
        patch(
            f"{SERVICE_MODULE}._find_catering_manager_for_project",
            return_value=contact,
        ),
        patch(
            f"{SERVICE_MODULE}.send_sms_notification",
            return_value=True,
        ),
    ):
        mock_dt.now.return_value = NOW_UTC
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = await send_catering_inquiry_reminders(session)

    # Both should qualify since Mar 22 is 2 days before Mar 24 in both timezones
    assert result.reminders_sent == 2


def test_format_single_request_message() -> None:
    """Single request produces a concise reminder."""
    req = _make_request()
    msg = format_catering_reminder_message([req])
    assert "2 days ago" in msg.lower()
    assert "Taylor" in msg
    assert "Party Size: 25" in msg


def test_format_multiple_requests_message() -> None:
    """Multiple requests produce a summary list."""
    req1 = _make_request()
    req2 = _make_request()
    msg = format_catering_reminder_message([req1, req2])
    assert "2 days ago" in msg.lower()
    assert "1." in msg
    assert "2." in msg


@pytest.mark.asyncio
async def test_sms_failure_records_error() -> None:
    """SMS send failure is recorded as an error but doesn't crash."""
    session = AsyncMock()
    req = _make_request()
    project = _make_project()
    contact = _make_contact()

    catering_repo = AsyncMock()
    catering_repo.list_inquiry_requests_in_date_range.return_value = [req]
    project_repo = AsyncMock()
    project_repo.list_projects_by_ids.return_value = [project]

    with (
        patch(f"{SERVICE_MODULE}.datetime") as mock_dt,
        patch(
            f"{SERVICE_MODULE}.CateringRequestRepositoryAsync",
            return_value=catering_repo,
        ),
        patch(
            f"{SERVICE_MODULE}.ProjectRepositoryAsync",
            return_value=project_repo,
        ),
        patch(
            f"{SERVICE_MODULE}._find_catering_manager_for_project",
            return_value=contact,
        ),
        patch(
            f"{SERVICE_MODULE}.send_sms_notification",
            return_value=False,
        ),
    ):
        mock_dt.now.return_value = NOW_UTC
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = await send_catering_inquiry_reminders(session)

    assert result.reminders_sent == 0
    assert result.success is False
    assert len(result.errors) == 1


# ---------------------------------------------------------------------------
# Apology SMS tests
# ---------------------------------------------------------------------------

# For apology tests: event was yesterday (Mar 23) in Chicago timezone.
# NOW_UTC is 2026-03-24 19:00 UTC = 2026-03-24 14:00 CDT, so yesterday = Mar 23.
YESTERDAY_LOCAL = date(2026, 3, 23)


def _make_apology_request(
    *,
    project_id: uuid.UUID = PROJECT_ID,
    event_date: date = YESTERDAY_LOCAL,
    event_time: time | None = None,
) -> CateringRequest:
    return CateringRequest(
        id=uuid.uuid4(),
        project_id=project_id,
        event_date=event_date,
        event_time=event_time,
        contact_name="Taylor",
        contact_phone_number="5551234567",
        party_size=25,
        status=RequestStatus.INQUIRY,
        idempotency_key=str(uuid.uuid4()),
        created_at=NOW_UTC - timedelta(days=7),  # created a week ago
    )


@pytest.mark.asyncio
async def test_apology_happy_path_sends_sms() -> None:
    """INQUIRY request with event_date yesterday -> sends apology to requester."""
    session = AsyncMock()
    req = _make_apology_request()
    project = _make_project()

    catering_repo = AsyncMock()
    catering_repo.list_inquiry_requests_by_event_date_range.return_value = [req]
    project_repo = AsyncMock()
    project_repo.list_projects_by_ids.return_value = [project]

    with (
        patch(f"{SERVICE_MODULE}.datetime") as mock_dt,
        patch(
            f"{SERVICE_MODULE}.CateringRequestRepositoryAsync",
            return_value=catering_repo,
        ),
        patch(
            f"{SERVICE_MODULE}.ProjectRepositoryAsync",
            return_value=project_repo,
        ),
        patch(
            f"{SERVICE_MODULE}.send_sms_notification",
            return_value=True,
        ) as mock_sms,
    ):
        mock_dt.now.return_value = NOW_UTC
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = await send_catering_inquiry_apologies(session)

    assert result.apologies_sent == 1
    assert result.success is True
    mock_sms.assert_called_once()
    # SMS sent to the requester's phone, not the catering manager
    assert mock_sms.call_args[0][0] == "5551234567"
    msg = mock_sms.call_args[0][1]
    assert "sorry" in msg.lower()
    assert "Taylor" in msg


@pytest.mark.asyncio
async def test_apology_no_candidates_returns_empty() -> None:
    """No INQUIRY requests with recent event dates -> no apologies sent."""
    session = AsyncMock()
    catering_repo = AsyncMock()
    catering_repo.list_inquiry_requests_by_event_date_range.return_value = []

    with (
        patch(f"{SERVICE_MODULE}.datetime") as mock_dt,
        patch(
            f"{SERVICE_MODULE}.CateringRequestRepositoryAsync",
            return_value=catering_repo,
        ),
    ):
        mock_dt.now.return_value = NOW_UTC
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = await send_catering_inquiry_apologies(session)

    assert result.apologies_sent == 0
    assert result.projects_checked == 0


@pytest.mark.asyncio
async def test_apology_event_two_days_ago_excluded() -> None:
    """Event that happened 2 days ago should NOT get an apology (only yesterday)."""
    session = AsyncMock()
    req = _make_apology_request(event_date=date(2026, 3, 22))  # 2 days ago
    project = _make_project()

    catering_repo = AsyncMock()
    catering_repo.list_inquiry_requests_by_event_date_range.return_value = [req]
    project_repo = AsyncMock()
    project_repo.list_projects_by_ids.return_value = [project]

    with (
        patch(f"{SERVICE_MODULE}.datetime") as mock_dt,
        patch(
            f"{SERVICE_MODULE}.CateringRequestRepositoryAsync",
            return_value=catering_repo,
        ),
        patch(
            f"{SERVICE_MODULE}.ProjectRepositoryAsync",
            return_value=project_repo,
        ),
        patch(f"{SERVICE_MODULE}.send_sms_notification") as mock_sms,
    ):
        mock_dt.now.return_value = NOW_UTC
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = await send_catering_inquiry_apologies(session)

    assert result.apologies_sent == 0
    mock_sms.assert_not_called()


@pytest.mark.asyncio
async def test_apology_event_today_excluded() -> None:
    """Event happening today should NOT get an apology."""
    session = AsyncMock()
    req = _make_apology_request(event_date=date(2026, 3, 24))  # today
    project = _make_project()

    catering_repo = AsyncMock()
    catering_repo.list_inquiry_requests_by_event_date_range.return_value = [req]
    project_repo = AsyncMock()
    project_repo.list_projects_by_ids.return_value = [project]

    with (
        patch(f"{SERVICE_MODULE}.datetime") as mock_dt,
        patch(
            f"{SERVICE_MODULE}.CateringRequestRepositoryAsync",
            return_value=catering_repo,
        ),
        patch(
            f"{SERVICE_MODULE}.ProjectRepositoryAsync",
            return_value=project_repo,
        ),
        patch(f"{SERVICE_MODULE}.send_sms_notification") as mock_sms,
    ):
        mock_dt.now.return_value = NOW_UTC
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = await send_catering_inquiry_apologies(session)

    assert result.apologies_sent == 0
    mock_sms.assert_not_called()


@pytest.mark.asyncio
async def test_apology_multiple_requests_sends_individual_sms() -> None:
    """Multiple qualifying requests -> individual apology SMS per requester."""
    session = AsyncMock()
    req1 = _make_apology_request()
    req2 = _make_apology_request()
    project = _make_project()

    catering_repo = AsyncMock()
    catering_repo.list_inquiry_requests_by_event_date_range.return_value = [req1, req2]
    project_repo = AsyncMock()
    project_repo.list_projects_by_ids.return_value = [project]

    with (
        patch(f"{SERVICE_MODULE}.datetime") as mock_dt,
        patch(
            f"{SERVICE_MODULE}.CateringRequestRepositoryAsync",
            return_value=catering_repo,
        ),
        patch(
            f"{SERVICE_MODULE}.ProjectRepositoryAsync",
            return_value=project_repo,
        ),
        patch(
            f"{SERVICE_MODULE}.send_sms_notification",
            return_value=True,
        ) as mock_sms,
    ):
        mock_dt.now.return_value = NOW_UTC
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = await send_catering_inquiry_apologies(session)

    assert result.apologies_sent == 2
    assert mock_sms.call_count == 2


@pytest.mark.asyncio
async def test_apology_sms_failure_records_error() -> None:
    """SMS send failure for apology is recorded as an error."""
    session = AsyncMock()
    req = _make_apology_request()
    project = _make_project()

    catering_repo = AsyncMock()
    catering_repo.list_inquiry_requests_by_event_date_range.return_value = [req]
    project_repo = AsyncMock()
    project_repo.list_projects_by_ids.return_value = [project]

    with (
        patch(f"{SERVICE_MODULE}.datetime") as mock_dt,
        patch(
            f"{SERVICE_MODULE}.CateringRequestRepositoryAsync",
            return_value=catering_repo,
        ),
        patch(
            f"{SERVICE_MODULE}.ProjectRepositoryAsync",
            return_value=project_repo,
        ),
        patch(
            f"{SERVICE_MODULE}.send_sms_notification",
            return_value=False,
        ),
    ):
        mock_dt.now.return_value = NOW_UTC
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = await send_catering_inquiry_apologies(session)

    assert result.apologies_sent == 0
    assert result.success is False
    assert len(result.errors) == 1


def test_format_apology_message() -> None:
    """Apology message includes requester name, event date, and project name."""
    req = _make_apology_request()
    msg = format_catering_apology_message(req, "Pal Bistro Downtown")
    assert "Taylor" in msg
    assert "sorry" in msg.lower()
    assert "March 23, 2026" in msg
    assert "Pal Bistro Downtown" in msg
