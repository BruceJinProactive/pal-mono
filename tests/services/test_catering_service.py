import asyncio
import sys
import uuid
from datetime import date, datetime
from types import ModuleType, SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
import sqlalchemy.engine
import sqlalchemy.ext.asyncio
import sqlalchemy.orm

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

from db.pal_repository.data_classes.contact import ContactData  # noqa: E402
from db.tables.catering_requests import CateringRequest, RequestStatus  # noqa: E402
from services.catering_service._implementation import (  # noqa: E402
    _build_customer_status_sms_message,
    _get_catering_business_name,
    _get_catering_store_phone_number,
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
            "services.catering_service._implementation._get_catering_store_phone_number",
            return_value="+15551234567",
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
        "Hi, your catering request with Pal Bistro for March 12, 2026 has been updated to Confirmed. Please call +15551234567 if you have any questions.",
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
            "services.catering_service._implementation._get_catering_store_phone_number",
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

    mock_send_sms.assert_called_once_with(
        updated_request.contact_phone_number,
        "Hi, your catering request with Pal Bistro for March 12, 2026 has been updated to Confirmed.",
    )


def test_update_catering_request_sends_sms_when_store_phone_lookup_fails() -> None:
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
            "services.catering_service._implementation._get_catering_store_phone_number",
            side_effect=RuntimeError("contact lookup failed"),
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
    mock_send_sms.assert_called_once_with(
        updated_request.contact_phone_number,
        "Hi, your catering request with Pal Bistro for March 12, 2026 has been updated to Confirmed.",
    )
    mock_warning.assert_called_once()


@pytest.mark.parametrize(
    ("status", "status_label"),
    [
        (RequestStatus.IN_PREPARATION, "In Prep"),
        (RequestStatus.READY, "Ready"),
    ],
)
def test_update_catering_request_sends_sms_for_new_lifecycle_statuses(
    status: RequestStatus,
    status_label: str,
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
            "services.catering_service._implementation._get_catering_store_phone_number",
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
        f"Hi, your catering request with Pal Bistro for March 12, 2026 has been updated to {status_label}.",
    )


@pytest.mark.parametrize(
    "status",
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
            "services.catering_service._implementation._get_catering_store_phone_number",
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


def test_get_catering_store_phone_number_prefers_catering_manager() -> None:
    session = AsyncMock()
    project_id = uuid.uuid4()

    with patch(
        "services.catering_service._implementation.contact_service.list_by_project",
        return_value=[
            _build_contact(role="general", phone_number="+15550000000"),
            _build_contact(role="catering_manager", phone_number="+15551111111"),
        ],
    ) as mock_list_contacts:
        phone_number = asyncio.run(
            _get_catering_store_phone_number(session, project_id)
        )

    assert phone_number == "+15551111111"
    mock_list_contacts.assert_called_once_with(session, project_id)


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


def test_build_customer_status_sms_message_for_in_prep() -> None:
    request = _build_request(status=RequestStatus.IN_PREPARATION)

    message = _build_customer_status_sms_message(request, "Pal Bistro")

    assert (
        message
        == "Hi, your catering request with Pal Bistro for March 12, 2026 has been updated to In Prep."
    )


def test_build_customer_status_sms_message_includes_store_phone_number() -> None:
    request = _build_request(status=RequestStatus.READY)

    message = _build_customer_status_sms_message(request, "Pal Bistro", "+15551234567")

    assert (
        message
        == "Hi, your catering request with Pal Bistro for March 12, 2026 has been updated to Ready. Please call +15551234567 if you have any questions."
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


@pytest.mark.parametrize(
    "status",
    [
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
