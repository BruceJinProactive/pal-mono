"""Tests for the public catering request detail API implementation."""

import sys
import uuid
from datetime import date, datetime, time, timezone
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
from db.pal_repository.data_classes.catering_request import (  # noqa: E402
    CateringRequestData,
)
from db.tables.catering_requests import FulfillmentType, RequestStatus  # noqa: E402
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
        party_size=25,
        status=RequestStatus.CONFIRMED.value,
        store_address="456 Store Ave",
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
    assert result.event_detail == "Lunch for 25 guests"
    assert result.event_fulfillment == FulfillmentType.DELIVERY
    assert result.store_address == "456 Store Ave"
    assert result.status == RequestStatus.CONFIRMED

    public_payload = result.model_dump()
    assert public_payload["contact_phone_number"] == "+15551234567"
    assert public_payload["store_address"] == "456 Store Ave"
    assert "project_id" not in public_payload
    assert "contact_id" not in public_payload
    assert "idempotency_key" not in public_payload
    assert "created_at" not in public_payload
    assert "updated_at" not in public_payload


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
