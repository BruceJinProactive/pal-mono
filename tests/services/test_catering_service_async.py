"""Tests for catering_service.create_catering_request_async."""

import sys
import uuid
from datetime import date, datetime, time, timezone
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

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

original_create_engine = sqlalchemy.engine.create_engine
original_create_async_engine = sqlalchemy.ext.asyncio.create_async_engine
original_sessionmaker = sqlalchemy.orm.sessionmaker
original_async_sessionmaker = sqlalchemy.ext.asyncio.async_sessionmaker

sqlalchemy.engine.create_engine = lambda *args, **kwargs: object()
sqlalchemy.ext.asyncio.create_async_engine = lambda *args, **kwargs: object()
sqlalchemy.orm.sessionmaker = lambda *args, **kwargs: lambda *a, **kw: None
sqlalchemy.ext.asyncio.async_sessionmaker = (
    lambda *args, **kwargs: lambda *a, **kw: None
)

from db.pal_repository.data_classes.catering_request import (  # noqa: E402
    CateringRequestData,
)
from db.tables.catering_request_activities import (  # noqa: E402
    CateringRequestActivityActorType,
    CateringRequestActivitySource,
    CateringRequestActivityType,
)
from db.tables.catering_requests import FulfillmentType, RequestStatus  # noqa: E402
from services.catering_service._implementation import (  # noqa: E402
    create_catering_request_async,
    get_public_catering_request_by_id,
    list_catering_request_activities,
    list_catering_requests_with_activities_by_project_id,
    update_catering_request,
)

sqlalchemy.engine.create_engine = original_create_engine
sqlalchemy.ext.asyncio.create_async_engine = original_create_async_engine
sqlalchemy.orm.sessionmaker = original_sessionmaker
sqlalchemy.ext.asyncio.async_sessionmaker = original_async_sessionmaker


def _make_catering_request_data(**overrides) -> CateringRequestData:
    defaults = {
        "id": uuid.uuid4(),
        "project_id": uuid.uuid4(),
        "event_date": date(2025, 12, 25),
        "event_time": time(14, 30),
        "event_address": "123 Main St",
        "event_detail": "50 pepperoni pizzas",
        "event_fulfillment": FulfillmentType.DELIVERY.value,
        "contact_name": "John Doe",
        "contact_phone_number": "+15551234567",
        "party_size": 30,
        "contact_id": None,
        "status": RequestStatus.LEAD.value,
        "idempotency_key": "idem-key-1",
        "created_at": datetime(2025, 6, 1, tzinfo=timezone.utc),
        "updated_at": datetime(2025, 6, 1, tzinfo=timezone.utc),
    }
    defaults.update(overrides)
    return CateringRequestData(**defaults)


def _make_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.mark.asyncio
async def test_creates_new_request_when_no_existing() -> None:
    session = _make_session()
    project_id = uuid.uuid4()
    account_id = uuid.uuid4()

    repo = AsyncMock()
    repo.get_by_idempotency_key.return_value = None
    persisted_request_id = uuid.uuid4()
    repo.create.return_value = persisted_request_id

    project_repo = AsyncMock()
    project_repo.get_project.return_value = SimpleNamespace(
        account_id=account_id, name="Test Project"
    )

    with (
        patch(
            "services.catering_service._implementation.CateringRequestRepositoryNew",
            return_value=repo,
        ),
        patch(
            "services.catering_service._implementation.ProjectRepositoryAsync",
            return_value=project_repo,
        ),
        patch(
            "services.catering_service._implementation.publish_event",
            return_value=True,
        ) as mock_publish,
    ):
        result = await create_catering_request_async(
            session=session,
            project_id=project_id,
            event_date=date(2025, 12, 25),
            contact_name="John Doe",
            contact_phone_number="+15551234567",
            event_time=time(14, 30),
            event_address="123 Main St",
            event_detail="50 pepperoni pizzas",
            event_fulfillment=FulfillmentType.DELIVERY,
            party_size=30,
            idempotency_key="idem-key-1",
        )

    assert isinstance(result, CateringRequestData)
    assert result.id == persisted_request_id
    assert result.project_id == project_id
    assert result.event_date == date(2025, 12, 25)
    repo.create.assert_called_once()
    mock_publish.assert_called_once()
    assert mock_publish.call_args.args[0].catering_request_id == persisted_request_id


@pytest.mark.asyncio
async def test_creates_activity_when_new_request_created() -> None:
    session = _make_session()
    project_id = uuid.uuid4()

    repo = AsyncMock()
    repo.get_by_idempotency_key.return_value = None
    persisted_request_id = uuid.uuid4()
    repo.create.return_value = persisted_request_id

    activity_repo = AsyncMock()
    activity_repo.create.side_effect = lambda activity: activity

    project_repo = AsyncMock()
    project_repo.get_project.return_value = SimpleNamespace(
        account_id=uuid.uuid4(), name="Test Project"
    )

    with (
        patch(
            "services.catering_service._implementation.CateringRequestRepositoryNew",
            return_value=repo,
        ),
        patch(
            "services.catering_service._implementation.CateringRequestActivityRepository",
            return_value=activity_repo,
        ),
        patch(
            "services.catering_service._implementation.ProjectRepositoryAsync",
            return_value=project_repo,
        ),
        patch(
            "services.catering_service._implementation.publish_event",
            return_value=True,
        ),
    ):
        await create_catering_request_async(
            session=session,
            project_id=project_id,
            event_date=date(2025, 12, 25),
            contact_name="John Doe",
            contact_phone_number="+15551234567",
            party_size=30,
            idempotency_key="idem-key-1",
        )

    activity_repo.create.assert_awaited_once()
    activity = activity_repo.create.call_args.args[0]
    assert activity.catering_request_id == persisted_request_id
    assert activity.project_id == project_id
    assert activity.activity_type == CateringRequestActivityType.REQUEST_CREATED
    assert activity.actor_type == CateringRequestActivityActorType.CUSTOMER
    assert activity.actor_display_name == "John Doe"
    assert activity.source == CateringRequestActivitySource.AI_AGENT
    assert activity.metadata["initial_fields"]["party_size"] == 30


@pytest.mark.asyncio
async def test_get_public_catering_request_by_id_returns_request() -> None:
    session = _make_session()
    catering_request_id = uuid.uuid4()
    catering_request = _make_catering_request_data(id=catering_request_id)

    repo = AsyncMock()
    repo.get_by_id.return_value = catering_request

    with patch(
        "services.catering_service._implementation.CateringRequestRepositoryNew",
        return_value=repo,
    ):
        result = await get_public_catering_request_by_id(
            session=session,
            catering_request_id=catering_request_id,
        )

    assert result == catering_request
    repo.get_by_id.assert_awaited_once_with(catering_request_id)


@pytest.mark.asyncio
async def test_get_public_catering_request_by_id_returns_none_when_missing() -> None:
    session = _make_session()
    catering_request_id = uuid.uuid4()

    repo = AsyncMock()
    repo.get_by_id.return_value = None

    with patch(
        "services.catering_service._implementation.CateringRequestRepositoryNew",
        return_value=repo,
    ):
        result = await get_public_catering_request_by_id(
            session=session,
            catering_request_id=catering_request_id,
        )

    assert result is None
    repo.get_by_id.assert_awaited_once_with(catering_request_id)


@pytest.mark.asyncio
async def test_update_catering_request_records_field_update_activity() -> None:
    session = _make_session()
    request_id = uuid.uuid4()
    project_id = uuid.uuid4()
    actor_id = uuid.uuid4()

    existing_request = SimpleNamespace(
        id=request_id,
        project_id=project_id,
        event_date=date(2025, 12, 25),
        contact_name="John Doe",
        contact_phone_number="+15551234567",
        event_time=time(14, 30),
        event_address="123 Main St",
        event_detail="50 pepperoni pizzas",
        event_fulfillment=FulfillmentType.DELIVERY,
        party_size=30,
        status=RequestStatus.LEAD,
    )
    updated_request = SimpleNamespace(
        id=request_id,
        project_id=project_id,
        event_date=date(2025, 12, 25),
        contact_name="John Doe",
        contact_phone_number="+15551234567",
        event_time=time(14, 30),
        event_address="123 Main St",
        event_detail="50 pepperoni pizzas",
        event_fulfillment=FulfillmentType.DELIVERY,
        party_size=45,
        status=RequestStatus.LEAD,
    )

    repo = AsyncMock()
    repo.get_catering_request_by_id.return_value = existing_request
    repo.update_catering_request.return_value = updated_request

    activity_repo = AsyncMock()
    activity_repo.create.side_effect = lambda activity: activity

    with (
        patch(
            "services.catering_service._implementation.CateringRequestRepositoryAsync",
            return_value=repo,
        ),
        patch(
            "services.catering_service._implementation.CateringRequestActivityRepository",
            return_value=activity_repo,
        ),
    ):
        result = await update_catering_request(
            session=session,
            catering_request_id=request_id,
            party_size=45,
            actor_id=actor_id,
            actor_display_name="Casey Manager",
        )

    assert result is updated_request
    activity_repo.create.assert_awaited_once()
    activity = activity_repo.create.call_args.args[0]
    assert activity.activity_type == CateringRequestActivityType.REQUEST_UPDATED
    assert activity.actor_id == actor_id
    assert activity.actor_display_name == "Casey Manager"
    assert activity.source == CateringRequestActivitySource.ADMIN_CONSOLE
    assert activity.metadata["changed_fields"] == {"party_size": {"old": 30, "new": 45}}
    session.refresh.assert_awaited_once_with(updated_request)


@pytest.mark.asyncio
async def test_list_catering_request_activities_returns_project_scoped_entries() -> (
    None
):
    session = _make_session()
    project_id = uuid.uuid4()
    catering_request_id = uuid.uuid4()
    activities = [object()]

    request_repo = AsyncMock()
    request_repo.get_by_id.return_value = _make_catering_request_data(
        id=catering_request_id,
        project_id=project_id,
    )

    activity_repo = AsyncMock()
    activity_repo.list_by_request.return_value = activities

    with (
        patch(
            "services.catering_service._implementation.CateringRequestRepositoryNew",
            return_value=request_repo,
        ),
        patch(
            "services.catering_service._implementation.CateringRequestActivityRepository",
            return_value=activity_repo,
        ),
    ):
        result = await list_catering_request_activities(
            session=session,
            project_id=project_id,
            catering_request_id=catering_request_id,
            limit=500,
        )

    assert result == activities
    activity_repo.list_by_request.assert_awaited_once_with(
        project_id=project_id,
        catering_request_id=catering_request_id,
        limit=100,
        before=None,
    )


@pytest.mark.asyncio
async def test_list_catering_request_activities_returns_none_for_wrong_project() -> (
    None
):
    session = _make_session()

    request_repo = AsyncMock()
    request_repo.get_by_id.return_value = _make_catering_request_data(
        project_id=uuid.uuid4()
    )

    activity_repo = AsyncMock()

    with (
        patch(
            "services.catering_service._implementation.CateringRequestRepositoryNew",
            return_value=request_repo,
        ),
        patch(
            "services.catering_service._implementation.CateringRequestActivityRepository",
            return_value=activity_repo,
        ),
    ):
        result = await list_catering_request_activities(
            session=session,
            project_id=uuid.uuid4(),
            catering_request_id=uuid.uuid4(),
        )

    assert result is None
    activity_repo.list_by_request.assert_not_called()


@pytest.mark.asyncio
async def test_list_catering_requests_with_activities_returns_embedded_timelines() -> (
    None
):
    session = _make_session()
    project_id = uuid.uuid4()
    catering_request = _make_catering_request_data(project_id=project_id)
    activities = [object()]

    request_repo = AsyncMock()
    request_repo.get_by_project_id.return_value = [catering_request]

    activity_repo = AsyncMock()
    activity_repo.list_by_request.return_value = activities

    with (
        patch(
            "services.catering_service._implementation.CateringRequestRepositoryNew",
            return_value=request_repo,
        ),
        patch(
            "services.catering_service._implementation.CateringRequestActivityRepository",
            return_value=activity_repo,
        ),
    ):
        result = await list_catering_requests_with_activities_by_project_id(
            session=session,
            project_id=project_id,
            activity_limit=500,
        )

    assert result == [(catering_request, activities)]
    request_repo.get_by_project_id.assert_awaited_once_with(project_id)
    activity_repo.list_by_request.assert_awaited_once_with(
        project_id=project_id,
        catering_request_id=catering_request.id,
        limit=100,
    )


@pytest.mark.asyncio
async def test_generates_idempotency_key_when_none() -> None:
    session = _make_session()
    project_id = uuid.uuid4()

    repo = AsyncMock()
    repo.get_by_idempotency_key.return_value = None
    repo.create.return_value = uuid.uuid4()

    project_repo = AsyncMock()
    project_repo.get_project.return_value = SimpleNamespace(
        account_id=uuid.uuid4(), name="Test Project"
    )

    with (
        patch(
            "services.catering_service._implementation.CateringRequestRepositoryNew",
            return_value=repo,
        ),
        patch(
            "services.catering_service._implementation.ProjectRepositoryAsync",
            return_value=project_repo,
        ),
        patch(
            "services.catering_service._implementation.publish_event",
            return_value=True,
        ),
    ):
        result = await create_catering_request_async(
            session=session,
            project_id=project_id,
            event_date=date(2025, 12, 25),
            contact_name="John Doe",
            contact_phone_number="+15551234567",
            idempotency_key=None,
        )

    assert isinstance(result, CateringRequestData)
    repo.get_by_idempotency_key.assert_called_once()
    call_arg = repo.get_by_idempotency_key.call_args[0][0]
    uuid.UUID(call_arg)


@pytest.mark.asyncio
async def test_returns_existing_when_no_updates_needed() -> None:
    session = _make_session()
    project_id = uuid.uuid4()
    existing_request = _make_catering_request_data(project_id=project_id)

    repo = AsyncMock()
    repo.get_by_idempotency_key.return_value = existing_request

    with patch(
        "services.catering_service._implementation.CateringRequestRepositoryNew",
        return_value=repo,
    ):
        result = await create_catering_request_async(
            session=session,
            project_id=project_id,
            event_date=date(2025, 12, 25),
            contact_name="John Doe",
            contact_phone_number="+15551234567",
            event_time=time(14, 30),
            event_address="123 Main St",
            event_detail="50 pepperoni pizzas",
            event_fulfillment=FulfillmentType.DELIVERY,
            party_size=30,
            idempotency_key="idem-key-1",
        )

    assert result is existing_request
    repo.update.assert_not_called()


@pytest.mark.asyncio
async def test_updates_existing_when_fields_differ() -> None:
    session = _make_session()
    project_id = uuid.uuid4()
    existing_request = _make_catering_request_data(
        project_id=project_id, party_size=30, contact_name="John Doe"
    )
    updated_request = _make_catering_request_data(
        project_id=project_id, party_size=50, contact_name="Jane Doe"
    )

    repo = AsyncMock()
    repo.get_by_idempotency_key.return_value = existing_request
    repo.update.return_value = updated_request

    with patch(
        "services.catering_service._implementation.CateringRequestRepositoryNew",
        return_value=repo,
    ):
        result = await create_catering_request_async(
            session=session,
            project_id=project_id,
            event_date=date(2025, 12, 25),
            contact_name="Jane Doe",
            contact_phone_number="+15551234567",
            event_time=time(14, 30),
            event_address="123 Main St",
            event_detail="50 pepperoni pizzas",
            event_fulfillment=FulfillmentType.DELIVERY,
            party_size=50,
            idempotency_key="idem-key-1",
        )

    assert result is updated_request
    repo.update.assert_called_once()


@pytest.mark.asyncio
async def test_skips_event_publishing_when_project_not_found() -> None:
    session = _make_session()
    project_id = uuid.uuid4()

    repo = AsyncMock()
    repo.get_by_idempotency_key.return_value = None
    repo.create.return_value = uuid.uuid4()

    project_repo = AsyncMock()
    project_repo.get_project.return_value = None

    with (
        patch(
            "services.catering_service._implementation.CateringRequestRepositoryNew",
            return_value=repo,
        ),
        patch(
            "services.catering_service._implementation.ProjectRepositoryAsync",
            return_value=project_repo,
        ),
        patch(
            "services.catering_service._implementation.publish_event",
            return_value=True,
        ) as mock_publish,
    ):
        result = await create_catering_request_async(
            session=session,
            project_id=project_id,
            event_date=date(2025, 12, 25),
            contact_name="John Doe",
            contact_phone_number="+15551234567",
            idempotency_key="idem-key-1",
        )

    assert isinstance(result, CateringRequestData)
    mock_publish.assert_not_called()


@pytest.mark.asyncio
async def test_logs_warning_when_event_publish_fails() -> None:
    session = _make_session()
    project_id = uuid.uuid4()

    repo = AsyncMock()
    repo.get_by_idempotency_key.return_value = None
    repo.create.return_value = uuid.uuid4()

    project_repo = AsyncMock()
    project_repo.get_project.return_value = SimpleNamespace(
        account_id=uuid.uuid4(), name="Test Project"
    )

    with (
        patch(
            "services.catering_service._implementation.CateringRequestRepositoryNew",
            return_value=repo,
        ),
        patch(
            "services.catering_service._implementation.ProjectRepositoryAsync",
            return_value=project_repo,
        ),
        patch(
            "services.catering_service._implementation.publish_event",
            return_value=False,
        ),
        patch(
            "services.catering_service._implementation.logger.warning"
        ) as mock_warning,
    ):
        result = await create_catering_request_async(
            session=session,
            project_id=project_id,
            event_date=date(2025, 12, 25),
            contact_name="John Doe",
            contact_phone_number="+15551234567",
            idempotency_key="idem-key-1",
        )

    assert isinstance(result, CateringRequestData)
    mock_warning.assert_called_once()


@pytest.mark.asyncio
async def test_does_not_update_when_new_value_is_none() -> None:
    """Fields with None new_value should not trigger an update."""
    session = _make_session()
    project_id = uuid.uuid4()
    existing_request = _make_catering_request_data(
        project_id=project_id,
        event_time=time(14, 30),
        event_address="123 Main St",
    )

    repo = AsyncMock()
    repo.get_by_idempotency_key.return_value = existing_request

    with patch(
        "services.catering_service._implementation.CateringRequestRepositoryNew",
        return_value=repo,
    ):
        result = await create_catering_request_async(
            session=session,
            project_id=project_id,
            event_date=date(2025, 12, 25),
            contact_name="John Doe",
            contact_phone_number="+15551234567",
            event_time=None,
            event_address=None,
            party_size=None,
            idempotency_key="idem-key-1",
        )

    assert result is existing_request
    repo.update.assert_not_called()
