import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.repositories.catering_request_repository import (
    CateringRequestRepository,
    CateringRequestRepositoryAsync,
)
from db.tables.catering_requests import CateringRequest


def _partial_request() -> CateringRequest:
    return CateringRequest(
        project_id=uuid.uuid4(),
        event_date=None,
        contact_name="Email Lead",
        contact_phone_number=None,
        contact_email="lead@example.com",
        idempotency_key=str(uuid.uuid4()),
    )


@pytest.mark.asyncio
async def test_async_create_persists_explicit_null_partial_lead_fields() -> None:
    session = AsyncMock()
    session.add = MagicMock()
    repo = CateringRequestRepositoryAsync(session)

    result = await repo.create_catering_request(_partial_request())

    assert result.__dict__["event_date"] is None
    assert result.__dict__["contact_phone_number"] is None
    assert result.contact_email == "lead@example.com"
    session.add.assert_called_once_with(result)


@pytest.mark.asyncio
async def test_async_update_clears_explicit_null_partial_lead_fields() -> None:
    existing_request = CateringRequest(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        event_date=date(2026, 6, 20),
        contact_name="Email Lead",
        contact_phone_number="+15551234567",
        contact_email="lead@example.com",
        idempotency_key=str(uuid.uuid4()),
    )
    updated_request = _partial_request()

    result_proxy = MagicMock()
    result_proxy.scalar_one_or_none.return_value = existing_request
    session = AsyncMock()
    session.execute.return_value = result_proxy
    repo = CateringRequestRepositoryAsync(session)

    result = await repo.update_catering_request(existing_request.id, updated_request)

    assert result is existing_request
    assert existing_request.event_date is None
    assert existing_request.contact_phone_number is None
    assert existing_request.contact_email == "lead@example.com"


def test_sync_create_persists_explicit_null_partial_lead_fields() -> None:
    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = None
    repo = CateringRequestRepository(session)

    result = repo.create_catering_request(_partial_request())

    assert result.__dict__["event_date"] is None
    assert result.__dict__["contact_phone_number"] is None
    assert result.contact_email == "lead@example.com"
    session.add.assert_called_once_with(result)


def test_sync_update_clears_explicit_null_partial_lead_fields() -> None:
    existing_request = CateringRequest(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        event_date=date(2026, 6, 20),
        contact_name="Email Lead",
        contact_phone_number="+15551234567",
        contact_email="lead@example.com",
        idempotency_key=str(uuid.uuid4()),
    )
    updated_request = _partial_request()

    result_proxy = MagicMock()
    result_proxy.scalar_one_or_none.return_value = existing_request
    session = MagicMock()
    session.execute.return_value = result_proxy
    repo = CateringRequestRepository(session)

    result = repo.update_catering_request(existing_request.id, updated_request)

    assert result is existing_request
    assert existing_request.event_date is None
    assert existing_request.contact_phone_number is None
    assert existing_request.contact_email == "lead@example.com"
