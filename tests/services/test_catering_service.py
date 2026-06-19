import asyncio
import sys
import uuid
from datetime import date, datetime
from types import ModuleType, SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import sqlalchemy.engine
import sqlalchemy.ext.asyncio
import sqlalchemy.orm

boto3_stub = ModuleType("boto3")
boto3_stub.__path__ = []
setattr(boto3_stub, "client", lambda *args, **kwargs: object())
sys.modules.setdefault("boto3", boto3_stub)

boto3_session_stub = ModuleType("boto3.session")
setattr(boto3_session_stub, "Session", lambda *args, **kwargs: object())
sys.modules.setdefault("boto3.session", boto3_session_stub)

aioboto3_stub = ModuleType("aioboto3")
sys.modules.setdefault("aioboto3", aioboto3_stub)

botocore_exceptions_stub = ModuleType("botocore.exceptions")
setattr(botocore_exceptions_stub, "ClientError", Exception)
sys.modules.setdefault("botocore.exceptions", botocore_exceptions_stub)

sqlalchemy.engine.create_engine = lambda *args, **kwargs: object()
sqlalchemy.ext.asyncio.create_async_engine = lambda *args, **kwargs: object()
sqlalchemy.orm.sessionmaker = lambda *args, **kwargs: lambda *a, **kw: None
sqlalchemy.ext.asyncio.async_sessionmaker = (
    lambda *args, **kwargs: lambda *a, **kw: None
)

from db.pal_repository.data_classes.contact import ContactData  # noqa: E402
from db.tables.catering_requests import (  # noqa: E402
    CateringRequest,
    FulfillmentType,
    RequestStatus,
)
from services.catering_service._implementation import (  # noqa: E402
    _build_customer_status_sms_message,
    _extract_catering_ai_phone_number,
    _find_and_assign_catering_manager,
    _format_catering_contact_summary,
    _get_catering_business_name,
    _get_catering_manager_phone_number,
    _get_catering_request_confirmation_url,
    _get_catering_store_phone_number,
    _is_catering_manager_role,
    _should_send_customer_status_sms,
    create_catering_request,
    format_catering_request_message,
    send_sms_notification,
    update_catering_request,
)


def _build_request(
    *,
    status: RequestStatus,
    phone_number: str | None = "4165550100",
    event_fulfillment: FulfillmentType | None = None,
) -> CateringRequest:
    return CateringRequest(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        event_date=date(2026, 3, 12),
        contact_name="Taylor",
        contact_phone_number=phone_number,
        event_fulfillment=event_fulfillment,
        status=status,
        idempotency_key=str(uuid.uuid4()),
    )


def _build_contact(
    *,
    role: str,
    phone_number: str,
) -> ContactData:
    return ContactData(
        id=uuid.uuid4(),
        name=f"{role} contact",
        phone_number=phone_number,
        role=role,
        created_at=datetime(2026, 3, 1),
    )


def _expected_confirmation_link(catering_request: CateringRequest) -> str:
    return (
        " View details: "
        f"https://console.palona.ai/catering-request/{catering_request.id}"
    )


@pytest.fixture(autouse=True)
def _set_default_runtime_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RUNTIME_ENV", raising=False)


def test_request_status_plan_lifecycle_values() -> None:
    assert [
        RequestStatus.LEAD.value,
        RequestStatus.PROPOSAL.value,
        RequestStatus.CONFIRMED.value,
        RequestStatus.LOCKED.value,
        RequestStatus.IN_PREPARATION.value,
        RequestStatus.READY.value,
        RequestStatus.COMPLETED.value,
        RequestStatus.CLOSED.value,
    ] == [
        "LEAD",
        "PROPOSAL",
        "CONFIRMED",
        "LOCKED",
        "IN_PREPARATION",
        "READY",
        "COMPLETED",
        "CLOSED",
    ]


def test_request_status_legacy_values_remain_supported() -> None:
    assert RequestStatus("INQUIRY") == RequestStatus.INQUIRY
    assert RequestStatus("QUOTE_SENT") == RequestStatus.QUOTE_SENT
    assert RequestStatus("IN_PREP") == RequestStatus.IN_PREP
    assert RequestStatus("FULFILLED") == RequestStatus.FULFILLED
    assert RequestStatus("CANCELLED") == RequestStatus.CANCELLED
    assert RequestStatus("ISSUE") == RequestStatus.ISSUE


def test_send_sms_notification_uses_default_catering_sender(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CATERING_SMS_SENDER_NUMBER", raising=False)

    with patch(
        "services.catering_service._implementation.send_message",
        return_value={"status": "scheduled"},
    ) as mock_send_message:
        assert send_sms_notification("4165550100", "Your catering order is ready")

    relay_message = mock_send_message.call_args.args[0]
    assert relay_message.sender_identifier == "+19803725662"


def test_create_catering_request_skips_event_for_partial_request_without_date() -> None:
    session = MagicMock()
    created_request = _build_request(status=RequestStatus.LEAD)
    setattr(created_request, "event_date", None)
    repo = MagicMock()
    repo.get_catering_request_by_idempotency_key.return_value = None
    repo.create_catering_request.return_value = created_request
    project_repo = MagicMock()
    project_repo.get_project.return_value = SimpleNamespace(account_id=uuid.uuid4())

    with (
        patch(
            "services.catering_service._implementation.SyncSessionLocal",
            return_value=session,
        ),
        patch(
            "services.catering_service._implementation.CateringRequestRepository",
            return_value=repo,
        ),
        patch(
            "services.catering_service._implementation.ProjectRepository",
            return_value=project_repo,
        ),
        patch(
            "services.catering_service._implementation.publish_event",
            new_callable=AsyncMock,
        ) as mock_publish,
        patch("services.catering_service._implementation.logger.info") as mock_info,
    ):
        result = create_catering_request(
            project_id=created_request.project_id,
            event_date=None,
            contact_name="Taylor",
            contact_phone_number=None,
            contact_email="taylor@example.com",
            idempotency_key=created_request.idempotency_key,
        )

    assert result is created_request
    mock_publish.assert_not_called()
    mock_info.assert_called_once()
    session.close.assert_called_once()


def test_format_catering_request_message_includes_email_for_partial_lead() -> None:
    catering_request = _build_request(
        status=RequestStatus.LEAD,
        phone_number=None,
    )
    setattr(catering_request, "event_date", None)
    catering_request.contact_email = "taylor@example.com"

    message = format_catering_request_message(catering_request)

    assert "Date: Not provided" in message
    assert "Phone: Not provided" in message
    assert "Email: taylor@example.com" in message


def test_format_catering_contact_summary_returns_name_without_channels() -> None:
    assert _format_catering_contact_summary("Taylor", None, None) == "Taylor"


def test_update_catering_request_sends_sms_for_confirmed_status() -> None:
    session = AsyncMock()
    existing_request = _build_request(status=RequestStatus.LEAD)
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
            "services.catering_service._implementation._get_catering_manager_phone_number",
            return_value="+15551234567",
        ),
        patch(
            "services.catering_service._implementation._get_catering_ai_phone_number",
            return_value="+15557654321",
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
    expected_message = (
        "Hi Taylor, your catering request with Pal Bistro for March 12, 2026 "
        "is confirmed. We'll reach out if we need any final details. "
        f"View details: https://console.palona.ai/catering-request/{updated_request.id} "
        "Questions? Call our catering manager at +15551234567."
    )
    mock_send_sms.assert_called_once_with(
        updated_request.contact_phone_number,
        expected_message,
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
            "services.catering_service._implementation._get_catering_manager_phone_number",
            return_value=None,
        ),
        patch(
            "services.catering_service._implementation._get_catering_ai_phone_number",
            return_value=None,
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

    expected_message = (
        "Hi Taylor, your catering request with Pal Bistro for March 12, 2026 "
        "is confirmed. We'll reach out if we need any final details."
        f"{_expected_confirmation_link(updated_request)}"
    )
    mock_send_sms.assert_called_once_with(
        updated_request.contact_phone_number,
        expected_message,
    )


def test_update_catering_request_sends_sms_when_contact_number_lookups_fail() -> None:
    session = AsyncMock()
    existing_request = _build_request(status=RequestStatus.LEAD)
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
            "services.catering_service._implementation._get_catering_manager_phone_number",
            side_effect=RuntimeError("contact lookup failed"),
        ),
        patch(
            "services.catering_service._implementation._get_catering_ai_phone_number",
            side_effect=RuntimeError("project lookup failed"),
        ),
        patch(
            "services.catering_service._implementation.send_sms_notification",
            return_value=True,
        ) as mock_send_sms,
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
    expected_message = (
        "Hi Taylor, your catering request with Pal Bistro for March 12, 2026 "
        "is confirmed. We'll reach out if we need any final details."
        f"{_expected_confirmation_link(updated_request)}"
    )
    mock_send_sms.assert_called_once_with(
        updated_request.contact_phone_number,
        expected_message,
    )
    assert mock_warning.call_count == 2


@pytest.mark.parametrize(
    ("status", "expected_message"),
    [
        (
            RequestStatus.IN_PREPARATION,
            (
                "Hi Taylor, Pal Bistro has started preparing your catering order "
                "for March 12, 2026. We'll keep you posted as your event gets "
                "closer."
            ),
        ),
        (
            RequestStatus.READY,
            (
                "Hi Taylor, your catering order from Pal Bistro for March 12, "
                "2026 is ready."
            ),
        ),
    ],
)
def test_update_catering_request_sends_sms_for_new_lifecycle_statuses(
    status: RequestStatus,
    expected_message: str,
) -> None:
    session = AsyncMock()
    existing_request = _build_request(status=RequestStatus.LEAD)
    updated_request = _build_request(status=status)
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
            "services.catering_service._implementation._get_catering_manager_phone_number",
            return_value=None,
        ),
        patch(
            "services.catering_service._implementation._get_catering_ai_phone_number",
            return_value=None,
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
                status=status,
            )
        )

    mock_send_sms.assert_called_once_with(
        updated_request.contact_phone_number,
        f"{expected_message}{_expected_confirmation_link(updated_request)}",
    )


@pytest.mark.parametrize(
    "status",
    [
        RequestStatus.PROPOSAL,
        RequestStatus.LOCKED,
        RequestStatus.COMPLETED,
        RequestStatus.FULFILLED,
        RequestStatus.CLOSED,
        RequestStatus.INQUIRY,
        RequestStatus.QUOTE_SENT,
        RequestStatus.IN_PREP,
        RequestStatus.CANCELLED,
        RequestStatus.ISSUE,
    ],
)
def test_update_catering_request_skips_sms_for_unsupported_status(
    status: RequestStatus,
) -> None:
    session = AsyncMock()
    existing_request = _build_request(status=RequestStatus.LEAD)
    updated_request = _build_request(status=status)
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
                status=status,
            )
        )

    mock_send_sms.assert_not_called()


def test_update_catering_request_skips_sms_when_status_not_requested() -> None:
    session = AsyncMock()
    existing_request = _build_request(status=RequestStatus.LEAD)
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


def test_update_catering_request_skips_sms_when_contact_phone_missing() -> None:
    session = AsyncMock()
    existing_request = _build_request(status=RequestStatus.LEAD)
    updated_request = _build_request(status=RequestStatus.CONFIRMED)
    updated_request.id = existing_request.id
    updated_request.project_id = existing_request.project_id
    updated_request.idempotency_key = existing_request.idempotency_key
    setattr(updated_request, "contact_phone_number", None)

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
                status=RequestStatus.CONFIRMED,
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
    existing_request = _build_request(status=RequestStatus.LEAD)
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
            "services.catering_service._implementation._get_catering_manager_phone_number",
            return_value=None,
        ),
        patch(
            "services.catering_service._implementation._get_catering_ai_phone_number",
            return_value=None,
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
    existing_request = _build_request(status=RequestStatus.LEAD)
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
    assert _should_send_customer_status_sms(RequestStatus.LEAD, None) is False


@pytest.mark.parametrize(
    "next_status",
    [
        RequestStatus.CONFIRMED,
        RequestStatus.IN_PREPARATION,
        RequestStatus.READY,
    ],
)
def test_should_send_customer_status_sms_returns_true_for_supported_status(
    next_status: RequestStatus,
) -> None:
    assert _should_send_customer_status_sms(RequestStatus.LEAD, next_status) is True


@pytest.mark.parametrize(
    "next_status",
    [
        RequestStatus.LEAD,
        RequestStatus.PROPOSAL,
        RequestStatus.LOCKED,
        RequestStatus.COMPLETED,
        RequestStatus.FULFILLED,
        RequestStatus.CLOSED,
        RequestStatus.INQUIRY,
        RequestStatus.QUOTE_SENT,
        RequestStatus.IN_PREP,
        RequestStatus.CANCELLED,
        RequestStatus.ISSUE,
    ],
)
def test_should_send_customer_status_sms_returns_false_for_unsupported_status(
    next_status: RequestStatus,
) -> None:
    assert _should_send_customer_status_sms(RequestStatus.LEAD, next_status) is False


def test_is_catering_manager_role_accepts_admin_console_catering_role() -> None:
    assert _is_catering_manager_role("catering") is True
    assert _is_catering_manager_role("catering_manager") is False
    assert _is_catering_manager_role(" general ") is False


def test_find_and_assign_catering_manager_accepts_catering_role() -> None:
    session = AsyncMock()
    request_id = uuid.uuid4()
    catering_request = _build_request(status=RequestStatus.LEAD)
    manager = _build_contact(role="catering", phone_number="+15551111111")
    repo = AsyncMock()

    with (
        patch(
            "services.catering_service._implementation.contact_service.list_by_project",
            return_value=[manager],
        ),
        patch(
            "services.catering_service._implementation.CateringRequestRepositoryAsync",
            return_value=repo,
        ),
    ):
        result = asyncio.run(
            _find_and_assign_catering_manager(
                session, catering_request, str(request_id)
            )
        )

    assert result is manager
    repo.update_catering_request.assert_called_once()


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


def test_get_catering_business_name_prefers_account_display_name() -> None:
    session = AsyncMock()
    project_repo = AsyncMock()
    project_repo.get_project.return_value = SimpleNamespace(
        display_name="Downtown Location",
        name="pal-bistro-downtown",
        account=SimpleNamespace(display_name="Pal Bistro", name="Pal Restaurant Group"),
    )

    with patch(
        "services.catering_service._implementation.ProjectRepositoryAsync",
        return_value=project_repo,
    ):
        business_name = asyncio.run(_get_catering_business_name(session, uuid.uuid4()))

    assert business_name == "Pal Bistro"


def test_get_catering_business_name_falls_back_to_account_name() -> None:
    session = AsyncMock()
    project_repo = AsyncMock()
    project_repo.get_project.return_value = SimpleNamespace(
        display_name="Downtown Location",
        name="pal-bistro-downtown",
        account=SimpleNamespace(display_name=" ", name="Pal Restaurant Group"),
    )

    with patch(
        "services.catering_service._implementation.ProjectRepositoryAsync",
        return_value=project_repo,
    ):
        business_name = asyncio.run(_get_catering_business_name(session, uuid.uuid4()))

    assert business_name == "Pal Restaurant Group"


def test_get_catering_business_name_falls_back_to_project_name() -> None:
    session = AsyncMock()
    project_repo = AsyncMock()
    project_repo.get_project.return_value = SimpleNamespace(
        display_name="Downtown Location",
        name="pal-bistro-downtown",
        account=SimpleNamespace(display_name=" ", name=" "),
    )

    with patch(
        "services.catering_service._implementation.ProjectRepositoryAsync",
        return_value=project_repo,
    ):
        business_name = asyncio.run(_get_catering_business_name(session, uuid.uuid4()))

    assert business_name == "Downtown Location"


def test_get_catering_business_name_returns_fallback_for_blank_project_names() -> None:
    session = AsyncMock()
    project_repo = AsyncMock()
    project_repo.get_project.return_value = SimpleNamespace(
        display_name=" ",
        name="",
        account=SimpleNamespace(display_name=" ", name=""),
    )

    with patch(
        "services.catering_service._implementation.ProjectRepositoryAsync",
        return_value=project_repo,
    ):
        business_name = asyncio.run(_get_catering_business_name(session, uuid.uuid4()))

    assert business_name == "the business"


def test_get_catering_store_phone_number_prefers_catering_role() -> None:
    session = AsyncMock()
    project_id = uuid.uuid4()

    with patch(
        "services.catering_service._implementation.contact_service.list_by_project",
        return_value=[
            _build_contact(role="general", phone_number="+15550000000"),
            _build_contact(role="catering", phone_number="+15551111111"),
        ],
    ) as mock_list_contacts:
        phone_number = asyncio.run(
            _get_catering_store_phone_number(session, project_id)
        )

    assert phone_number == "+15551111111"
    mock_list_contacts.assert_called_once_with(session, project_id)


def test_get_catering_store_phone_number_ignores_catering_manager_role() -> None:
    session = AsyncMock()

    with patch(
        "services.catering_service._implementation.contact_service.list_by_project",
        return_value=[
            _build_contact(role="general", phone_number="+15550000000"),
            _build_contact(role="catering_manager", phone_number="+15552222222"),
        ],
    ):
        phone_number = asyncio.run(
            _get_catering_store_phone_number(session, uuid.uuid4())
        )

    assert phone_number == "+15550000000"


def test_get_catering_store_phone_number_uses_single_contact_any_role() -> None:
    session = AsyncMock()

    with patch(
        "services.catering_service._implementation.contact_service.list_by_project",
        return_value=[
            _build_contact(role="manager", phone_number=" +15553333333 "),
        ],
    ):
        phone_number = asyncio.run(
            _get_catering_store_phone_number(session, uuid.uuid4())
        )

    assert phone_number == "+15553333333"


def test_get_catering_store_phone_number_falls_back_to_general() -> None:
    session = AsyncMock()

    with patch(
        "services.catering_service._implementation.contact_service.list_by_project",
        return_value=[
            _build_contact(role="manager", phone_number="+15550000000"),
            _build_contact(role="general", phone_number="+15552222222"),
        ],
    ):
        phone_number = asyncio.run(
            _get_catering_store_phone_number(session, uuid.uuid4())
        )

    assert phone_number == "+15552222222"


def test_get_catering_store_phone_number_returns_none_without_matching_role() -> None:
    session = AsyncMock()

    with patch(
        "services.catering_service._implementation.contact_service.list_by_project",
        return_value=[
            _build_contact(role="manager", phone_number="+15550000000"),
            _build_contact(role="owner", phone_number="+15551111111"),
        ],
    ):
        phone_number = asyncio.run(
            _get_catering_store_phone_number(session, uuid.uuid4())
        )

    assert phone_number is None


def test_get_catering_manager_phone_number_uses_catering_role_only() -> None:
    session = AsyncMock()
    project_id = uuid.uuid4()

    with patch(
        "services.catering_service._implementation.contact_service.list_by_project",
        return_value=[
            _build_contact(role="general", phone_number="+15550000000"),
            _build_contact(role="catering", phone_number=" +15551111111 "),
        ],
    ):
        phone_number = asyncio.run(
            _get_catering_manager_phone_number(session, project_id)
        )

    assert phone_number == "+15551111111"


def test_extract_catering_ai_phone_number_prefers_sms_channel() -> None:
    assert (
        _extract_catering_ai_phone_number(
            ["voice:+15550000000", "sms:+15551111111", "phone:+15552222222"]
        )
        == "+15551111111"
    )


def test_build_customer_status_sms_message_for_in_prep() -> None:
    request = _build_request(
        status=RequestStatus.IN_PREPARATION,
        event_fulfillment=FulfillmentType.DELIVERY,
    )

    message = _build_customer_status_sms_message(request, "Pal Bistro")

    expected_message = (
        "Hi Taylor, Pal Bistro has started preparing your catering order for "
        "March 12, 2026. We'll keep you posted as it gets closer to delivery."
        f"{_expected_confirmation_link(request)}"
    )
    assert message == expected_message


def test_build_customer_status_sms_message_prefers_manager_number() -> None:
    request = _build_request(
        status=RequestStatus.READY,
        event_fulfillment=FulfillmentType.PICKUP,
    )

    message = _build_customer_status_sms_message(
        request, "Pal Bistro", "+15551234567", "+15557654321"
    )

    expected_message = (
        "Hi Taylor, your catering order from Pal Bistro for March 12, 2026 "
        "is ready for pickup."
        f"{_expected_confirmation_link(request)}"
        " Questions? Call our catering manager at +15551234567."
    )
    assert message == expected_message


def test_build_customer_status_sms_message_uses_ai_number_only_without_manager() -> (
    None
):
    request = _build_request(
        status=RequestStatus.READY,
        event_fulfillment=FulfillmentType.PICKUP,
    )

    message = _build_customer_status_sms_message(
        request, "Pal Bistro", None, "+15557654321"
    )

    expected_message = (
        "Hi Taylor, your catering order from Pal Bistro for March 12, 2026 "
        "is ready for pickup."
        f"{_expected_confirmation_link(request)}"
        " Questions? Call +15557654321."
    )
    assert message == expected_message


def test_build_customer_status_sms_message_for_ready() -> None:
    request = _build_request(status=RequestStatus.READY)

    message = _build_customer_status_sms_message(request, "Pal Bistro")

    expected_message = (
        "Hi Taylor, your catering order from Pal Bistro for March 12, 2026 is ready."
        f"{_expected_confirmation_link(request)}"
    )
    assert message == expected_message


def test_build_customer_status_sms_message_for_missing_event_date() -> None:
    request = cast(
        CateringRequest,
        SimpleNamespace(
            id=uuid.uuid4(),
            status=RequestStatus.CONFIRMED,
            event_date=None,
        ),
    )

    message = _build_customer_status_sms_message(request, "Pal Bistro")

    expected_message = (
        "Hi, your catering request with Pal Bistro is confirmed. "
        "We'll reach out if we need any final details."
        f"{_expected_confirmation_link(request)}"
    )
    assert message == expected_message


@pytest.mark.parametrize(
    ("runtime_env", "expected_host"),
    [
        ("prd", "console.palona.ai"),
        ("lat", "lat-console.palona.ai"),
        ("stg", "stg-console.palona.ai"),
        ("dev", "console.palona.ai"),
    ],
)
def test_get_catering_request_confirmation_url_uses_environment_host(
    runtime_env: str,
    expected_host: str,
) -> None:
    request_id = uuid.uuid4()

    with patch.dict("os.environ", {"RUNTIME_ENV": runtime_env}):
        url = _get_catering_request_confirmation_url(request_id)

    assert url == f"https://{expected_host}/catering-request/{request_id}"


@pytest.mark.parametrize(
    "status",
    [
        RequestStatus.LEAD,
        RequestStatus.PROPOSAL,
        RequestStatus.IN_PREP,
        RequestStatus.QUOTE_SENT,
        RequestStatus.CANCELLED,
    ],
)
def test_build_customer_status_sms_message_raises_for_unsupported_status(
    status: RequestStatus,
) -> None:
    request = _build_request(status=status)

    with pytest.raises(
        ValueError, match="Unsupported catering status for customer SMS"
    ):
        _build_customer_status_sms_message(request, "Pal Bistro")
