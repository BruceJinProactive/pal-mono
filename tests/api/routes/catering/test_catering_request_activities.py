"""Tests for catering request activity route wiring."""

import sys
import uuid
from datetime import date, datetime, timezone
from types import ModuleType
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

from api.routes.catering import _implementation  # noqa: E402
from api.schemas.catering.catering import CreateCateringRequestRequest  # noqa: E402
from db.pal_repository.data_classes.catering_request import (  # noqa: E402
    CateringRequestData,
)
from db.pal_repository.data_classes.catering_request_activity import (  # noqa: E402
    CateringRequestActivityData,
)
from db.tables.catering_request_activities import (  # noqa: E402
    CateringRequestActivityActorType,
    CateringRequestActivitySource,
    CateringRequestActivityType,
)
from db.tables.catering_requests import RequestStatus  # noqa: E402
from services.auth_types import UserContext, UserRole  # noqa: E402

sqlalchemy.engine.create_engine = original_create_engine
sqlalchemy.ext.asyncio.create_async_engine = original_create_async_engine
sqlalchemy.orm.sessionmaker = original_sessionmaker
sqlalchemy.ext.asyncio.async_sessionmaker = original_async_sessionmaker


def _make_context() -> UserContext:
    return UserContext(
        username=str(uuid.uuid4()),
        email="manager@example.com",
        groups=[],
        display_name="Casey Manager",
        role=UserRole.AccountManager,
    )


def _make_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    return session


def _make_activity_data(
    request_id: uuid.UUID,
    project_id: uuid.UUID,
) -> CateringRequestActivityData:
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    return CateringRequestActivityData(
        id=uuid.uuid4(),
        catering_request_id=request_id,
        project_id=project_id,
        activity_type=CateringRequestActivityType.STATUS_CHANGED,
        actor_type=CateringRequestActivityActorType.INTERNAL_USER,
        actor_display_name="Casey Manager",
        description="Moved request from LEAD to PROPOSAL.",
        source=CateringRequestActivitySource.ADMIN_CONSOLE,
        occurred_at=now,
        created_at=now,
        metadata={"from_status": "LEAD", "to_status": "PROPOSAL"},
    )


@pytest.mark.asyncio
async def test_create_project_catering_request_uses_internal_actor_for_activity() -> (
    None
):
    session = _make_session()
    project_id = uuid.uuid4()
    request_id = uuid.uuid4()
    context = _make_context()
    created_request = CateringRequestData(
        id=request_id,
        project_id=project_id,
        event_date=date(2026, 6, 15),
        contact_name="Maya Acme",
        contact_phone_number="+15551234567",
        status=RequestStatus.LEAD.value,
        idempotency_key="idem-key-1",
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        party_size=45,
    )

    with patch(
        "api.routes.catering._implementation.create_catering_request_async",
        return_value=created_request,
    ) as mock_create:
        result = await _implementation.create_project_catering_request(
            project_id=project_id,
            request=CreateCateringRequestRequest(
                event_date=date(2026, 6, 15),
                contact_name="Maya Acme",
                contact_phone_number="+15551234567",
                party_size=45,
                idempotency_key="idem-key-1",
            ),
            context=context,
            session=session,
        )

    assert result.id == request_id
    mock_create.assert_awaited_once()
    assert mock_create.call_args.kwargs["activity_actor_type"] == (
        CateringRequestActivityActorType.INTERNAL_USER
    )
    assert mock_create.call_args.kwargs["activity_actor_id"] == uuid.UUID(
        context.username
    )
    assert mock_create.call_args.kwargs["activity_actor_display_name"] == (
        "Casey Manager"
    )
    assert (
        mock_create.call_args.kwargs["activity_source"]
        == CateringRequestActivitySource.ADMIN_CONSOLE
    )


@pytest.mark.asyncio
async def test_list_project_catering_requests_embeds_activities_when_requested() -> (
    None
):
    session = _make_session()
    project_id = uuid.uuid4()
    request_id = uuid.uuid4()
    context = _make_context()
    catering_request = CateringRequestData(
        id=request_id,
        project_id=project_id,
        event_date=date(2026, 6, 15),
        contact_name="Maya Acme",
        contact_phone_number="+15551234567",
        status=RequestStatus.PROPOSAL.value,
        idempotency_key="idem-key-1",
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        party_size=45,
    )
    activity = _make_activity_data(request_id, project_id)

    with patch(
        "api.routes.catering._implementation.list_catering_requests_with_activities_by_project_id",
        return_value=[(catering_request, [activity])],
    ) as mock_list:
        result = await _implementation.list_project_catering_requests(
            project_id=project_id,
            include_activities=True,
            activity_limit=50,
            context=context,
            session=session,
        )

    mock_list.assert_awaited_once_with(
        session=session,
        project_id=project_id,
        activity_limit=50,
    )
    assert len(result.catering_requests) == 1
    assert result.catering_requests[0].id == request_id
    assert result.catering_requests[0].activities[0].id == activity.id
    assert result.catering_requests[0].activities[0].metadata == {
        "from_status": "LEAD",
        "to_status": "PROPOSAL",
    }
