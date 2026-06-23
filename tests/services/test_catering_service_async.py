"""Tests for catering_service.create_catering_request_async."""

import sys
import uuid
from datetime import date, datetime, time, timezone
from decimal import Decimal
from types import ModuleType, SimpleNamespace
from typing import Any
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

from db.pal_repository.data_classes.catering_menu import CateringMenuData  # noqa: E402
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
    delete_catering_request,
    get_catering_request_by_id,
    get_public_catering_request_by_id,
    list_catering_menu_items_by_project_id,
    list_catering_request_activities,
    list_catering_requests_with_activities_by_project_id,
    update_catering_menu_item,
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
        "contact_email": "john@example.com",
        "party_size": 30,
        "contact_id": None,
        "status": RequestStatus.LEAD.value,
        "idempotency_key": "idem-key-1",
        "created_at": datetime(2025, 6, 1, tzinfo=timezone.utc),
        "updated_at": datetime(2025, 6, 1, tzinfo=timezone.utc),
    }
    defaults.update(overrides)
    return CateringRequestData(**defaults)


def _make_catering_menu_data(**overrides: Any) -> CateringMenuData:
    defaults = {
        "id": uuid.uuid4(),
        "project_id": uuid.uuid4(),
        "account_id": uuid.uuid4(),
        "item_name": "Sandwich platter",
        "item_price": Decimal("145.50"),
        "created_at": datetime(2026, 6, 1, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 6, 1, tzinfo=timezone.utc),
    }
    defaults.update(overrides)
    return CateringMenuData(**defaults)


def _make_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    return session


def _set_empty_catering_history(repo: AsyncMock) -> None:
    repo.get_customer_history_by_project_id_and_phone_or_email.return_value = (
        SimpleNamespace(
            request_count=0,
            last_request_at=None,
        )
    )


def _patch_empty_order_history() -> Any:
    order_repo = AsyncMock()
    order_repo.get_customer_history_by_project_id_and_phone.return_value = (
        SimpleNamespace(order_count=0, last_order_at=None)
    )
    return patch(
        "services.catering_service._implementation.OrderRepositoryNew",
        return_value=order_repo,
    )


@pytest.mark.asyncio
async def test_list_catering_menu_items_by_project_id_uses_repository() -> None:
    session = _make_session()
    project_id = uuid.uuid4()
    menu_item = _make_catering_menu_data(project_id=project_id)
    repo = AsyncMock()
    repo.list_by_project_id.return_value = [menu_item]

    with patch(
        "services.catering_service._implementation.CateringMenuRepository",
        return_value=repo,
    ) as repo_cls:
        result = await list_catering_menu_items_by_project_id(session, project_id)

    assert result == [menu_item]
    repo_cls.assert_called_once_with(session)
    repo.list_by_project_id.assert_awaited_once_with(project_id)


@pytest.mark.asyncio
async def test_update_catering_menu_item_passes_only_provided_fields() -> None:
    session = _make_session()
    project_id = uuid.uuid4()
    menu_item_id = uuid.uuid4()
    menu_item = _make_catering_menu_data(id=menu_item_id)
    repo = AsyncMock()
    repo.update.return_value = menu_item

    with patch(
        "services.catering_service._implementation.CateringMenuRepository",
        return_value=repo,
    ):
        result = await update_catering_menu_item(
            session,
            menu_item_id,
            project_id=project_id,
            item_price=Decimal("155.00"),
        )

    assert result == menu_item
    repo.update.assert_awaited_once_with(
        menu_item_id,
        project_id=project_id,
        item_price=Decimal("155.00"),
    )


@pytest.mark.asyncio
async def test_creates_new_request_when_no_existing() -> None:
    session = _make_session()
    project_id = uuid.uuid4()
    account_id = uuid.uuid4()

    repo = AsyncMock()
    repo.get_by_idempotency_key.return_value = None
    persisted_request_id = uuid.uuid4()
    repo.create.return_value = persisted_request_id
    repo.get_customer_history_by_project_id_and_phone_or_email.return_value = (
        SimpleNamespace(
            request_count=2,
            last_request_at=datetime(2025, 5, 1, tzinfo=timezone.utc),
        )
    )

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
            "services.catering_service._implementation.OrderRepositoryNew",
            return_value=SimpleNamespace(
                get_customer_history_by_project_id_and_phone=AsyncMock(
                    return_value=SimpleNamespace(
                        order_count=3,
                        last_order_at=datetime(2025, 5, 15, tzinfo=timezone.utc),
                    )
                )
            ),
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
            contact_email="john@example.com",
            event_fulfillment=FulfillmentType.DELIVERY,
            party_size=30,
            estimated_order_value=Decimal("500.00"),
            confirmed_order_value=Decimal("525.00"),
            deposit_requirement_value=Decimal("100.00"),
            deposit_received_value=Decimal("50.00"),
            idempotency_key="idem-key-1",
        )

    assert isinstance(result, CateringRequestData)
    assert result.id == persisted_request_id
    assert result.project_id == project_id
    assert result.event_date == date(2025, 12, 25)
    assert result.prior_catering_request_count == 2
    assert result.prior_order_count == 3
    assert result.last_catering_request_at == datetime(2025, 5, 1, tzinfo=timezone.utc)
    assert result.last_order_at == datetime(2025, 5, 15, tzinfo=timezone.utc)
    assert result.estimated_order_value == Decimal("500.00")
    assert result.confirmed_order_value == Decimal("525.00")
    assert result.deposit_requirement_value == Decimal("100.00")
    assert result.deposit_received_value == Decimal("50.00")
    repo.get_customer_history_by_project_id_and_phone_or_email.assert_awaited_once_with(
        project_id,
        "+15551234567",
        "john@example.com",
    )
    repo.create.assert_called_once()
    mock_publish.assert_called_once()
    assert mock_publish.call_args.args[0].catering_request_id == persisted_request_id


@pytest.mark.asyncio
async def test_creates_partial_request_without_event_date_or_phone() -> None:
    session = _make_session()
    project_id = uuid.uuid4()

    repo = AsyncMock()
    repo.get_by_idempotency_key.return_value = None
    persisted_request_id = uuid.uuid4()
    repo.create.return_value = persisted_request_id

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
        ) as mock_publish,
    ):
        result = await create_catering_request_async(
            session=session,
            project_id=project_id,
            event_date=None,
            contact_name="Avery Lead",
            contact_phone_number=None,
            contact_email="avery@example.com",
            idempotency_key="partial-lead-1",
        )

    assert result.id == persisted_request_id
    assert result.event_date is None
    assert result.contact_phone_number is None
    assert result.contact_email == "avery@example.com"
    created_data = repo.create.call_args.args[0]
    assert created_data.event_date is None
    assert created_data.contact_phone_number is None
    assert created_data.contact_email == "avery@example.com"
    mock_publish.assert_not_called()


@pytest.mark.asyncio
async def test_creates_activity_when_new_request_created() -> None:
    session = _make_session()
    project_id = uuid.uuid4()

    repo = AsyncMock()
    repo.get_by_idempotency_key.return_value = None
    persisted_request_id = uuid.uuid4()
    repo.create.return_value = persisted_request_id
    _set_empty_catering_history(repo)

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
        _patch_empty_order_history(),
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
            activity_source=CateringRequestActivitySource.CUSTOMER_VOICE,
        )

    activity_repo.create.assert_awaited_once()
    activity = activity_repo.create.call_args.args[0]
    assert activity.catering_request_id == persisted_request_id
    assert activity.project_id == project_id
    assert activity.activity_type == CateringRequestActivityType.REQUEST_CREATED
    assert activity.actor_type == CateringRequestActivityActorType.CUSTOMER
    assert activity.actor_display_name == "John Doe"
    assert activity.source == CateringRequestActivitySource.CUSTOMER_VOICE
    assert activity.metadata["initial_fields"]["party_size"] == 30


@pytest.mark.asyncio
async def test_get_public_catering_request_by_id_returns_request() -> None:
    session = _make_session()
    catering_request_id = uuid.uuid4()
    catering_request = _make_catering_request_data(id=catering_request_id)

    repo = AsyncMock()
    repo.get_by_id.return_value = catering_request

    project_repo = AsyncMock()
    project_repo.get_project.return_value = SimpleNamespace(
        address="456 Store Ave",
        channel_identifiers=["voice:+15550000000", "sms:+15557654321"],
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
            "services.catering_service._implementation.contact_service.list_by_project",
            return_value=[
                SimpleNamespace(role="catering", phone_number=" +15551234567 ")
            ],
        ),
    ):
        result = await get_public_catering_request_by_id(
            session=session,
            catering_request_id=catering_request_id,
        )

    assert result is not None
    assert result.id == catering_request_id
    assert result.contact_phone_number == "+15551234567"
    assert result.event_address == "123 Main St"
    assert result.store_address == "456 Store Ave"
    assert result.catering_manager_phone_number == "+15551234567"
    assert result.catering_ai_phone_number == "+15557654321"
    repo.get_by_id.assert_awaited_once_with(catering_request_id)
    project_repo.get_project.assert_awaited_once_with(catering_request.project_id)


@pytest.mark.asyncio
async def test_get_public_catering_request_by_id_returns_partial_request() -> None:
    session = _make_session()
    catering_request_id = uuid.uuid4()
    catering_request = _make_catering_request_data(
        id=catering_request_id,
        event_date=None,
        contact_phone_number=None,
        contact_email="avery@example.com",
    )

    repo = AsyncMock()
    repo.get_by_id.return_value = catering_request

    project_repo = AsyncMock()
    project_repo.get_project.return_value = SimpleNamespace(
        address="456 Store Ave",
        channel_identifiers=[],
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
            "services.catering_service._implementation.contact_service.list_by_project",
            return_value=[],
        ),
    ):
        result = await get_public_catering_request_by_id(
            session=session,
            catering_request_id=catering_request_id,
        )

    assert result is not None
    assert result.event_date is None
    assert result.contact_phone_number is None
    assert result.contact_email == "avery@example.com"
    assert result.catering_manager_phone_number is None
    assert result.catering_ai_phone_number is None


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
async def test_get_catering_request_by_id_returns_internal_request() -> None:
    session = _make_session()
    catering_request_id = uuid.uuid4()
    catering_request = _make_catering_request_data(id=catering_request_id)

    repo = AsyncMock()
    repo.get_by_id.return_value = catering_request

    with patch(
        "services.catering_service._implementation.CateringRequestRepositoryNew",
        return_value=repo,
    ):
        result = await get_catering_request_by_id(
            session=session,
            catering_request_id=catering_request_id,
        )

    assert result is catering_request
    repo.get_by_id.assert_awaited_once_with(catering_request_id)


@pytest.mark.asyncio
async def test_delete_catering_request_deletes_timeline_then_request() -> None:
    session = _make_session()
    catering_request_id = uuid.uuid4()
    catering_request = _make_catering_request_data(id=catering_request_id)

    request_repo = AsyncMock()
    request_repo.get_by_id.return_value = catering_request
    request_repo.delete_by_id.return_value = catering_request

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
        result = await delete_catering_request(
            session=session,
            catering_request_id=catering_request_id,
        )

    assert result is catering_request
    request_repo.get_by_id.assert_awaited_once_with(catering_request_id)
    activity_repo.delete_by_request.assert_awaited_once_with(
        project_id=catering_request.project_id,
        catering_request_id=catering_request.id,
    )
    request_repo.delete_by_id.assert_awaited_once_with(catering_request_id)


@pytest.mark.asyncio
async def test_delete_catering_request_returns_none_when_missing() -> None:
    session = _make_session()
    catering_request_id = uuid.uuid4()

    request_repo = AsyncMock()
    request_repo.get_by_id.return_value = None

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
        result = await delete_catering_request(
            session=session,
            catering_request_id=catering_request_id,
        )

    assert result is None
    activity_repo.delete_by_request.assert_not_called()
    request_repo.delete_by_id.assert_not_called()


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
        contact_email="john@example.com",
        event_time=time(14, 30),
        event_address="123 Main St",
        event_detail="50 pepperoni pizzas",
        event_fulfillment=FulfillmentType.DELIVERY,
        party_size=30,
        prior_catering_request_count=2,
        prior_order_count=5,
        estimated_order_value=None,
        confirmed_order_value=None,
        deposit_requirement_value=None,
        deposit_received_value=None,
        status=RequestStatus.LEAD,
    )
    updated_request = SimpleNamespace(
        id=request_id,
        project_id=project_id,
        event_date=date(2025, 12, 25),
        contact_name="John Doe",
        contact_phone_number="+15551234567",
        contact_email="john@example.com",
        event_time=time(14, 30),
        event_address="123 Main St",
        event_detail="50 pepperoni pizzas",
        event_fulfillment=FulfillmentType.DELIVERY,
        party_size=45,
        prior_catering_request_count=4,
        prior_order_count=8,
        estimated_order_value=None,
        confirmed_order_value=None,
        deposit_requirement_value=None,
        deposit_received_value=None,
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
            prior_catering_request_count=4,
            prior_order_count=8,
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
    updated_model = repo.update_catering_request.call_args.args[1]
    assert updated_model.party_size == 45
    assert updated_model.prior_catering_request_count == 4
    assert updated_model.prior_order_count == 8
    assert activity.metadata["changed_fields"] == {
        "party_size": {"old": 30, "new": 45},
        "prior_catering_request_count": {"old": 2, "new": 4},
        "prior_order_count": {"old": 5, "new": 8},
    }
    session.refresh.assert_awaited_once_with(updated_request)


@pytest.mark.asyncio
async def test_update_catering_request_clears_nullable_lead_fields() -> None:
    session = _make_session()
    request_id = uuid.uuid4()
    project_id = uuid.uuid4()

    existing_request = SimpleNamespace(
        id=request_id,
        project_id=project_id,
        event_date=date(2025, 12, 25),
        contact_name="John Doe",
        contact_phone_number="+15551234567",
        contact_email="john@example.com",
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
        event_date=None,
        contact_name="John Doe",
        contact_phone_number=None,
        contact_email=None,
        event_time=time(14, 30),
        event_address="123 Main St",
        event_detail="50 pepperoni pizzas",
        event_fulfillment=FulfillmentType.DELIVERY,
        party_size=30,
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
            event_date=None,
            contact_phone_number=None,
            contact_email=None,
        )

    assert result is updated_request
    updated_model = repo.update_catering_request.call_args.args[1]
    assert updated_model.event_date is None
    assert updated_model.contact_phone_number is None
    assert updated_model.contact_email is None
    activity = activity_repo.create.call_args.args[0]
    assert activity.metadata["changed_fields"]["event_date"]["new"] is None
    assert activity.metadata["changed_fields"]["contact_phone_number"]["new"] is None
    assert activity.metadata["changed_fields"]["contact_email"]["new"] is None


@pytest.mark.asyncio
async def test_update_catering_request_ignores_null_non_nullable_fields() -> None:
    session = _make_session()
    request_id = uuid.uuid4()
    project_id = uuid.uuid4()

    existing_request = SimpleNamespace(
        id=request_id,
        project_id=project_id,
        event_date=date(2025, 12, 25),
        contact_name="John Doe",
        contact_phone_number="+15551234567",
        contact_email="john@example.com",
        event_time=time(14, 30),
        event_address="123 Main St",
        event_detail="50 pepperoni pizzas",
        event_fulfillment=FulfillmentType.DELIVERY,
        party_size=30,
        status=RequestStatus.LEAD,
    )
    updated_request = SimpleNamespace(**vars(existing_request))

    repo = AsyncMock()
    repo.get_catering_request_by_id.return_value = existing_request
    repo.update_catering_request.return_value = updated_request

    activity_repo = AsyncMock()

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
            contact_name=None,
            prior_catering_request_count=None,
            prior_order_count=None,
            status=None,
        )

    assert result is updated_request
    updated_model = repo.update_catering_request.call_args.args[1]
    assert "contact_name" not in updated_model.__dict__
    assert "prior_catering_request_count" not in updated_model.__dict__
    assert "prior_order_count" not in updated_model.__dict__
    assert "status" not in updated_model.__dict__
    activity_repo.create.assert_not_called()


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
    _set_empty_catering_history(repo)

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
        _patch_empty_order_history(),
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
    _set_empty_catering_history(repo)

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
        _patch_empty_order_history(),
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
    _set_empty_catering_history(repo)

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
        _patch_empty_order_history(),
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
