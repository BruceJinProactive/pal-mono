"""Tests for the public catering request detail API implementation."""

import sys
import uuid
from datetime import date, datetime, time, timezone
from decimal import Decimal
from types import ModuleType
from unittest.mock import AsyncMock, patch

import pytest
import sqlalchemy.engine
import sqlalchemy.ext.asyncio
import sqlalchemy.orm
from fastapi import HTTPException

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

import api.routes.catering as catering_routes  # noqa: E402
from api.routes.catering import _implementation  # noqa: E402
from db.pal_repository.data_classes.catering_menu import CateringMenuData  # noqa: E402
from db.pal_repository.data_classes.catering_request import (  # noqa: E402
    CateringRequestData,
)
from db.tables.catering_requests import FulfillmentType, RequestStatus  # noqa: E402
from services.auth_types import UserContext, UserRole  # noqa: E402
from services.catering_service._implementation import (  # noqa: E402
    PublicCateringRequestDetails,
)

sqlalchemy.engine.create_engine = original_create_engine
sqlalchemy.ext.asyncio.create_async_engine = original_create_async_engine
sqlalchemy.orm.sessionmaker = original_sessionmaker
sqlalchemy.ext.asyncio.async_sessionmaker = original_async_sessionmaker


def _make_public_catering_request_details(
    catering_request_id: uuid.UUID,
) -> PublicCateringRequestDetails:
    return PublicCateringRequestDetails(
        id=catering_request_id,
        event_date=date(2026, 6, 15),
        event_time=time(12, 30),
        event_address="123 Main St",
        event_detail="Lunch for 25 guests",
        event_fulfillment=FulfillmentType.DELIVERY.value,
        contact_name="Taylor Guest",
        contact_phone_number="+15551234567",
        contact_email="taylor@example.com",
        party_size=25,
        status=RequestStatus.CONFIRMED.value,
        store_address="456 Store Ave",
        catering_manager_phone_number="+15551234567",
        catering_ai_phone_number="+15557654321",
    )


def _make_catering_request_data(
    *,
    catering_request_id: uuid.UUID,
    project_id: uuid.UUID,
) -> CateringRequestData:
    return CateringRequestData(
        id=catering_request_id,
        project_id=project_id,
        event_date=date(2026, 6, 15),
        contact_name="Taylor Guest",
        contact_phone_number="+15551234567",
        status=RequestStatus.CONFIRMED.value,
        idempotency_key="idem-key-1",
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )


def _make_catering_menu_data(
    *,
    menu_item_id: uuid.UUID,
    project_id: uuid.UUID,
) -> CateringMenuData:
    return CateringMenuData(
        id=menu_item_id,
        project_id=project_id,
        account_id=uuid.uuid4(),
        item_name="Sandwich platter",
        item_price=Decimal("145.50"),
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )


def _make_user_context() -> UserContext:
    return UserContext(
        username=str(uuid.uuid4()),
        email="manager@example.com",
        groups=[],
        display_name="Catering Manager",
        role=UserRole.AccountManager,
    )


@pytest.mark.asyncio
async def test_get_public_catering_request_returns_public_safe_fields() -> None:
    session = AsyncMock()
    catering_request_id = uuid.uuid4()
    catering_request = _make_public_catering_request_details(catering_request_id)

    with patch(
        "api.routes.catering._implementation.get_public_catering_request_by_id",
        return_value=catering_request,
    ):
        result = await _implementation.get_public_catering_request(
            catering_request_id=catering_request_id,
            session=session,
        )

    assert result.id == catering_request_id
    assert result.contact_name == "Taylor Guest"
    assert result.contact_phone_number == "+15551234567"
    assert result.contact_email == "taylor@example.com"
    assert result.event_detail == "Lunch for 25 guests"
    assert result.event_fulfillment == FulfillmentType.DELIVERY
    assert result.store_address == "456 Store Ave"
    assert result.catering_manager_phone_number == "+15551234567"
    assert result.catering_ai_phone_number == "+15557654321"
    assert result.status == RequestStatus.CONFIRMED

    public_payload = result.model_dump()
    assert public_payload["contact_phone_number"] == "+15551234567"
    assert public_payload["contact_email"] == "taylor@example.com"
    assert public_payload["store_address"] == "456 Store Ave"
    assert public_payload["catering_manager_phone_number"] == "+15551234567"
    assert public_payload["catering_ai_phone_number"] == "+15557654321"
    assert "project_id" not in public_payload
    assert "contact_id" not in public_payload
    assert "idempotency_key" not in public_payload
    assert "created_at" not in public_payload
    assert "updated_at" not in public_payload


@pytest.mark.asyncio
async def test_list_project_catering_menu_items_returns_project_items() -> None:
    session = AsyncMock()
    project_id = uuid.uuid4()
    menu_item_id = uuid.uuid4()
    menu_item = _make_catering_menu_data(
        menu_item_id=menu_item_id,
        project_id=project_id,
    )

    with patch(
        "api.routes.catering._implementation.list_catering_menu_items_by_project_id",
        return_value=[menu_item],
    ):
        result = await _implementation.list_project_catering_menu_items(
            project_id=project_id,
            context=AsyncMock(),
            session=session,
        )

    assert result.menu_items[0].id == menu_item_id
    assert result.menu_items[0].project_id == project_id
    assert result.menu_items[0].item_name == "Sandwich platter"
    assert result.menu_items[0].item_price == Decimal("145.50")


@pytest.mark.asyncio
async def test_update_catering_menu_item_returns_updated_item() -> None:
    session = AsyncMock()
    project_id = uuid.uuid4()
    menu_item_id = uuid.uuid4()
    menu_item = _make_catering_menu_data(
        menu_item_id=menu_item_id,
        project_id=project_id,
    )

    with patch(
        "api.routes.catering._implementation.update_catering_menu_item_impl",
        return_value=menu_item,
    ) as update_impl:
        result = await _implementation.update_catering_menu_item(
            project_id=project_id,
            menu_item_id=menu_item_id,
            request=_implementation.UpdateCateringMenuItemRequest(
                item_name="Sandwich platter",
                item_price=Decimal("145.50"),
            ),
            context=AsyncMock(),
            session=session,
        )

    update_impl.assert_awaited_once_with(
        session=session,
        project_id=project_id,
        menu_item_id=menu_item_id,
        item_name="Sandwich platter",
        item_price=Decimal("145.50"),
    )
    assert result.id == menu_item_id
    assert result.item_price == Decimal("145.50")


@pytest.mark.asyncio
async def test_update_catering_menu_item_raises_not_found() -> None:
    session = AsyncMock()
    project_id = uuid.uuid4()
    menu_item_id = uuid.uuid4()

    with patch(
        "api.routes.catering._implementation.update_catering_menu_item_impl",
        return_value=None,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await _implementation.update_catering_menu_item(
                project_id=project_id,
                menu_item_id=menu_item_id,
                request=_implementation.UpdateCateringMenuItemRequest(
                    item_name="Missing item",
                ),
                context=AsyncMock(),
                session=session,
            )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_list_project_catering_menu_items_route_delegates_to_implementation() -> (
    None
):
    session = AsyncMock()
    project_id = uuid.uuid4()
    context = _make_user_context()
    response = _implementation.CateringMenuItemListResponse(menu_items=[])

    with patch(
        "api.routes.catering._implementation.list_project_catering_menu_items",
        return_value=response,
    ) as mock_list:
        result = await catering_routes.list_project_catering_menu_items(
            project_id=project_id,
            context=context,
            session=session,
        )

    assert result is response
    mock_list.assert_awaited_once_with(project_id, context, session)


@pytest.mark.asyncio
async def test_update_catering_menu_item_route_delegates_to_implementation() -> None:
    session = AsyncMock()
    project_id = uuid.uuid4()
    menu_item_id = uuid.uuid4()
    context = _make_user_context()
    request = _implementation.UpdateCateringMenuItemRequest(
        item_name="New platter",
        item_price=Decimal("155.00"),
    )
    response = _implementation.CateringMenuItem(
        id=menu_item_id,
        project_id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        item_name="New platter",
        item_price=Decimal("155.00"),
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 6, 2, tzinfo=timezone.utc),
    )

    with patch(
        "api.routes.catering._implementation.update_catering_menu_item",
        return_value=response,
    ) as mock_update:
        result = await catering_routes.update_catering_menu_item(
            project_id=project_id,
            menu_item_id=menu_item_id,
            request=request,
            context=context,
            session=session,
        )

    assert result is response
    mock_update.assert_awaited_once_with(
        project_id, menu_item_id, request, context, session
    )


@pytest.mark.asyncio
async def test_get_public_catering_request_allows_partial_lead_fields() -> None:
    session = AsyncMock()
    catering_request_id = uuid.uuid4()
    catering_request = PublicCateringRequestDetails(
        id=catering_request_id,
        event_date=None,
        contact_name="Taylor Guest",
        contact_phone_number=None,
        contact_email="taylor@example.com",
        status=RequestStatus.LEAD.value,
        store_address="456 Store Ave",
    )

    with patch(
        "api.routes.catering._implementation.get_public_catering_request_by_id",
        return_value=catering_request,
    ):
        result = await _implementation.get_public_catering_request(
            catering_request_id=catering_request_id,
            session=session,
        )

    assert result.event_date is None
    assert result.contact_phone_number is None
    assert result.contact_email == "taylor@example.com"


@pytest.mark.asyncio
async def test_get_public_catering_request_raises_404_when_missing() -> None:
    session = AsyncMock()
    catering_request_id = uuid.uuid4()

    with patch(
        "api.routes.catering._implementation.get_public_catering_request_by_id",
        return_value=None,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await _implementation.get_public_catering_request(
                catering_request_id=catering_request_id,
                session=session,
            )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_catering_request_deletes_owned_request() -> None:
    session = AsyncMock()
    project_id = uuid.uuid4()
    catering_request_id = uuid.uuid4()
    catering_request = _make_catering_request_data(
        catering_request_id=catering_request_id,
        project_id=project_id,
    )

    with (
        patch(
            "api.routes.catering._implementation.get_catering_request_by_id",
            return_value=catering_request,
        ) as mock_get,
        patch(
            "api.routes.catering._implementation.delete_catering_request_impl",
            return_value=catering_request,
        ) as mock_delete,
    ):
        result = await _implementation.delete_catering_request(
            project_id=project_id,
            catering_request_id=catering_request_id,
            context=object(),  # type: ignore[arg-type]
            session=session,
        )

    assert result == {"status": "deleted"}
    mock_get.assert_awaited_once_with(
        session=session,
        catering_request_id=catering_request_id,
    )
    mock_delete.assert_awaited_once_with(
        session=session,
        catering_request_id=catering_request_id,
    )


@pytest.mark.asyncio
async def test_delete_catering_request_raises_404_when_missing() -> None:
    session = AsyncMock()
    catering_request_id = uuid.uuid4()

    with patch(
        "api.routes.catering._implementation.get_catering_request_by_id",
        return_value=None,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await _implementation.delete_catering_request(
                project_id=uuid.uuid4(),
                catering_request_id=catering_request_id,
                context=object(),  # type: ignore[arg-type]
                session=session,
            )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_catering_request_raises_404_for_wrong_project() -> None:
    session = AsyncMock()
    catering_request_id = uuid.uuid4()
    catering_request = _make_catering_request_data(
        catering_request_id=catering_request_id,
        project_id=uuid.uuid4(),
    )

    with (
        patch(
            "api.routes.catering._implementation.get_catering_request_by_id",
            return_value=catering_request,
        ),
        patch(
            "api.routes.catering._implementation.delete_catering_request_impl",
        ) as mock_delete,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await _implementation.delete_catering_request(
                project_id=uuid.uuid4(),
                catering_request_id=catering_request_id,
                context=object(),  # type: ignore[arg-type]
                session=session,
            )

    assert exc_info.value.status_code == 404
    mock_delete.assert_not_called()


@pytest.mark.asyncio
async def test_delete_catering_request_raises_404_when_delete_loses_race() -> None:
    session = AsyncMock()
    project_id = uuid.uuid4()
    catering_request_id = uuid.uuid4()
    catering_request = _make_catering_request_data(
        catering_request_id=catering_request_id,
        project_id=project_id,
    )

    with (
        patch(
            "api.routes.catering._implementation.get_catering_request_by_id",
            return_value=catering_request,
        ),
        patch(
            "api.routes.catering._implementation.delete_catering_request_impl",
            return_value=None,
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await _implementation.delete_catering_request(
                project_id=project_id,
                catering_request_id=catering_request_id,
                context=object(),  # type: ignore[arg-type]
                session=session,
            )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_catering_request_route_delegates_to_implementation() -> None:
    session = AsyncMock()
    project_id = uuid.uuid4()
    catering_request_id = uuid.uuid4()
    context = object()

    with patch(
        "api.routes.catering._implementation.delete_catering_request",
        return_value={"status": "deleted"},
    ) as mock_delete:
        result = await catering_routes.delete_catering_request(
            project_id=project_id,
            catering_request_id=catering_request_id,
            context=context,  # type: ignore[arg-type]
            session=session,
        )

    assert result == {"status": "deleted"}
    mock_delete.assert_awaited_once_with(
        project_id,
        catering_request_id,
        context,
        session,
    )
