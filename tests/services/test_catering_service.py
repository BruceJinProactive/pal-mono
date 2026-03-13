import asyncio
import sys
import uuid
from datetime import date
from types import ModuleType, SimpleNamespace
from typing import cast
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

from db.tables.catering_requests import CateringRequest, RequestStatus
from services.catering_service._implementation import (
    _build_customer_status_sms_message,
    _get_catering_business_name,
    _should_send_customer_status_sms,
    update_catering_request,
)


def _build_request(
    *,
    status: RequestStatus,
    phone_number: str = "4165550100",
) -> CateringRequest:
    return CateringRequest(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        event_date=date(2026, 3, 12),
        contact_name="Taylor",
        contact_phone_number=phone_number,
        status=status,
        idempotency_key=str(uuid.uuid4()),
    )


def test_update_catering_request_sends_sms_for_tracked_status_transition() -> None:
    session = AsyncMock()
    existing_request = _build_request(status=RequestStatus.INQUIRY)
    updated_request = _build_request(status=RequestStatus.CONFIRMED)
    updated_request.id = existing_request.id
    updated_request.project_id = existing_request.project_id
    updated_request.idempotency_key = existing_request.idempotency_key

    repo = AsyncMock()
    repo.get_catering_request_by_id.return_value = existing_request
    repo.update_catering_request.return_value = updated_request
    project_repo = AsyncMock()
    project_repo.get_project.return_value = SimpleNamespace(
        display_name="Pal Bistro", name="pal-bistro"
    )

    with (
        patch(
            "services.catering_service._implementation.CateringRequestRepositoryAsync",
            return_value=repo,
        ),
        patch(
            "services.catering_service._implementation.ProjectRepositoryAsync",
            return_value=project_repo,
        ),
        patch(
            "services.catering_service._implementation.send_sms_notification",
            return_value=True,
        ) as mock_send_sms,
    ):
        result = asyncio.run(
            update_catering_request(
                session=session,
                catering_request_id=existing_request.id,
                status=RequestStatus.CONFIRMED,
            )
        )

    assert result is updated_request
    mock_send_sms.assert_called_once_with(
        updated_request.contact_phone_number,
        "Hi, your catering request with Pal Bistro for March 12, 2026 has been updated to Confirmed.",
    )


def test_update_catering_request_sends_sms_when_status_is_re_requested() -> None:
    session = AsyncMock()
    existing_request = _build_request(status=RequestStatus.CONFIRMED)
    updated_request = _build_request(status=RequestStatus.CONFIRMED)
    updated_request.id = existing_request.id
    updated_request.project_id = existing_request.project_id
    updated_request.idempotency_key = existing_request.idempotency_key

    repo = AsyncMock()
    repo.get_catering_request_by_id.return_value = existing_request
    repo.update_catering_request.return_value = updated_request
    project_repo = AsyncMock()
    project_repo.get_project.return_value = SimpleNamespace(
        display_name="Pal Bistro", name="pal-bistro"
    )

    with (
        patch(
            "services.catering_service._implementation.CateringRequestRepositoryAsync",
            return_value=repo,
        ),
        patch(
            "services.catering_service._implementation.ProjectRepositoryAsync",
            return_value=project_repo,
        ),
        patch(
            "services.catering_service._implementation.send_sms_notification",
            return_value=True,
        ) as mock_send_sms,
    ):
        asyncio.run(
            update_catering_request(
                session=session,
                catering_request_id=existing_request.id,
                status=RequestStatus.CONFIRMED,
            )
        )

    mock_send_sms.assert_called_once_with(
        updated_request.contact_phone_number,
        "Hi, your catering request with Pal Bistro for March 12, 2026 has been updated to Confirmed.",
    )


def test_update_catering_request_skips_sms_for_untracked_status_transition() -> None:
    session = AsyncMock()
    existing_request = _build_request(status=RequestStatus.INQUIRY)
    updated_request = _build_request(status=RequestStatus.IN_PREP)
    updated_request.id = existing_request.id
    updated_request.project_id = existing_request.project_id
    updated_request.idempotency_key = existing_request.idempotency_key

    repo = AsyncMock()
    repo.get_catering_request_by_id.return_value = existing_request
    repo.update_catering_request.return_value = updated_request

    with (
        patch(
            "services.catering_service._implementation.CateringRequestRepositoryAsync",
            return_value=repo,
        ),
        patch(
            "services.catering_service._implementation.send_sms_notification",
            return_value=True,
        ) as mock_send_sms,
    ):
        asyncio.run(
            update_catering_request(
                session=session,
                catering_request_id=existing_request.id,
                status=RequestStatus.IN_PREP,
            )
        )

    mock_send_sms.assert_not_called()


def test_update_catering_request_skips_sms_when_status_not_requested() -> None:
    session = AsyncMock()
    existing_request = _build_request(status=RequestStatus.INQUIRY)
    updated_request = _build_request(status=RequestStatus.CONFIRMED)
    updated_request.id = existing_request.id
    updated_request.project_id = existing_request.project_id
    updated_request.idempotency_key = existing_request.idempotency_key

    repo = AsyncMock()
    repo.get_catering_request_by_id.return_value = existing_request
    repo.update_catering_request.return_value = updated_request

    with (
        patch(
            "services.catering_service._implementation.CateringRequestRepositoryAsync",
            return_value=repo,
        ),
        patch(
            "services.catering_service._implementation.send_sms_notification",
            return_value=True,
        ) as mock_send_sms,
    ):
        result = asyncio.run(
            update_catering_request(
                session=session,
                catering_request_id=existing_request.id,
                contact_name="Updated Taylor",
            )
        )

    assert result is updated_request
    mock_send_sms.assert_not_called()


def test_update_catering_request_raises_when_request_is_missing() -> None:
    session = AsyncMock()
    missing_request_id = uuid.uuid4()

    repo = AsyncMock()
    repo.get_catering_request_by_id.return_value = None

    with patch(
        "services.catering_service._implementation.CateringRequestRepositoryAsync",
        return_value=repo,
    ):
        with pytest.raises(
            ValueError, match=f"Catering request {missing_request_id} not found"
        ):
            asyncio.run(
                update_catering_request(
                    session=session,
                    catering_request_id=missing_request_id,
                    status=RequestStatus.CONFIRMED,
                )
            )


def test_update_catering_request_logs_warning_when_sms_send_fails() -> None:
    session = AsyncMock()
    existing_request = _build_request(status=RequestStatus.INQUIRY)
    updated_request = _build_request(status=RequestStatus.CONFIRMED)
    updated_request.id = existing_request.id
    updated_request.project_id = existing_request.project_id
    updated_request.idempotency_key = existing_request.idempotency_key

    repo = AsyncMock()
    repo.get_catering_request_by_id.return_value = existing_request
    repo.update_catering_request.return_value = updated_request
    project_repo = AsyncMock()
    project_repo.get_project.return_value = SimpleNamespace(
        display_name="Pal Bistro", name="pal-bistro"
    )

    with (
        patch(
            "services.catering_service._implementation.CateringRequestRepositoryAsync",
            return_value=repo,
        ),
        patch(
            "services.catering_service._implementation.ProjectRepositoryAsync",
            return_value=project_repo,
        ),
        patch(
            "services.catering_service._implementation.send_sms_notification",
            return_value=False,
        ),
        patch(
            "services.catering_service._implementation.logger.warning"
        ) as mock_warning,
    ):
        asyncio.run(
            update_catering_request(
                session=session,
                catering_request_id=existing_request.id,
                status=RequestStatus.CONFIRMED,
            )
        )

    mock_warning.assert_called_once()


def test_update_catering_request_swallows_notification_exceptions() -> None:
    session = AsyncMock()
    existing_request = _build_request(status=RequestStatus.INQUIRY)
    updated_request = _build_request(status=RequestStatus.CONFIRMED)
    updated_request.id = existing_request.id
    updated_request.project_id = existing_request.project_id
    updated_request.idempotency_key = existing_request.idempotency_key

    repo = AsyncMock()
    repo.get_catering_request_by_id.return_value = existing_request
    repo.update_catering_request.return_value = updated_request

    with (
        patch(
            "services.catering_service._implementation.CateringRequestRepositoryAsync",
            return_value=repo,
        ),
        patch(
            "services.catering_service._implementation._get_catering_business_name",
            side_effect=RuntimeError("lookup failed"),
        ),
        patch(
            "services.catering_service._implementation.logger.warning"
        ) as mock_warning,
    ):
        result = asyncio.run(
            update_catering_request(
                session=session,
                catering_request_id=existing_request.id,
                status=RequestStatus.CONFIRMED,
            )
        )

    assert result is updated_request
    mock_warning.assert_called_once()


def test_should_send_customer_status_sms_returns_false_for_none_next_status() -> None:
    assert _should_send_customer_status_sms(RequestStatus.INQUIRY, None) is False


def test_should_send_customer_status_sms_returns_true_for_supported_status() -> None:
    assert (
        _should_send_customer_status_sms(RequestStatus.INQUIRY, RequestStatus.CONFIRMED)
        is True
    )


def test_get_catering_business_name_returns_fallback_when_project_missing() -> None:
    session = AsyncMock()
    project_repo = AsyncMock()
    project_repo.get_project.return_value = None

    with patch(
        "services.catering_service._implementation.ProjectRepositoryAsync",
        return_value=project_repo,
    ):
        business_name = asyncio.run(_get_catering_business_name(session, uuid.uuid4()))

    assert business_name == "the business"


def test_get_catering_business_name_returns_fallback_for_blank_project_names() -> None:
    session = AsyncMock()
    project_repo = AsyncMock()
    project_repo.get_project.return_value = SimpleNamespace(display_name=" ", name="")

    with patch(
        "services.catering_service._implementation.ProjectRepositoryAsync",
        return_value=project_repo,
    ):
        business_name = asyncio.run(_get_catering_business_name(session, uuid.uuid4()))

    assert business_name == "the business"


def test_build_customer_status_sms_message_for_quote_sent() -> None:
    request = _build_request(status=RequestStatus.QUOTE_SENT)

    message = _build_customer_status_sms_message(request, "Pal Bistro")

    assert (
        message
        == "Hi, your catering request with Pal Bistro has been reviewed and the status has been updated to 'Quote Sent'."
    )


def test_build_customer_status_sms_message_for_cancelled() -> None:
    request = _build_request(status=RequestStatus.CANCELLED)

    message = _build_customer_status_sms_message(request, "Pal Bistro")

    assert (
        message
        == "Hi, your catering request with Pal Bistro for March 12, 2026 has been updated to Cancelled. Please reach out if you have any questions."
    )


def test_build_customer_status_sms_message_for_ready() -> None:
    request = _build_request(status=RequestStatus.READY)

    message = _build_customer_status_sms_message(request, "Pal Bistro")

    assert (
        message
        == "Hi, your catering request with Pal Bistro for March 12, 2026 has been updated to Ready."
    )


def test_build_customer_status_sms_message_for_missing_event_date() -> None:
    request = cast(
        CateringRequest,
        SimpleNamespace(
            status=RequestStatus.CONFIRMED,
            event_date=None,
        ),
    )

    message = _build_customer_status_sms_message(request, "Pal Bistro")

    assert (
        message
        == "Hi, your catering request with Pal Bistro has been updated to Confirmed."
    )


def test_build_customer_status_sms_message_raises_for_unsupported_status() -> None:
    request = _build_request(status=RequestStatus.IN_PREP)

    with pytest.raises(
        ValueError, match="Unsupported catering status for customer SMS"
    ):
        _build_customer_status_sms_message(request, "Pal Bistro")
