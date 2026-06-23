from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.toast_checkout_session import ToastCheckoutSessionRepository
from db.tables.toast_checkout_sessions import ToastCheckoutSession


class _FakeScalarResult:
    def __init__(self, row: Any) -> None:
        self.row = row

    def scalar_one_or_none(self) -> Any:
        return self.row


@pytest.mark.asyncio
async def test_toast_checkout_session_repository_writes_and_reads_session() -> None:
    fake_session = SimpleNamespace(
        add=MagicMock(),
        flush=AsyncMock(),
        execute=AsyncMock(),
    )
    repo = ToastCheckoutSessionRepository(cast(AsyncSession, fake_session))
    token = uuid.uuid4()
    conversation_id = uuid.uuid4()
    expires_at = datetime.now(timezone.utc)

    row = await repo.create(
        token=token,
        conversation_id=conversation_id,
        external_reference_id="ref-123",
        order_external_id="ORDER-123",
        request_payload={"type": "payment_checkout"},
        session_payload={},
        checkout_url="https://checkout.test",
        expires_at=expires_at,
    )

    fake_session.add.assert_called_once_with(row)
    assert row.token == token
    assert row.conversation_id == conversation_id
    assert row.external_reference_id == "ref-123"
    assert row.order_external_id == "ORDER-123"
    assert row.status == "processing"

    ready_expires_at = datetime.now(timezone.utc)
    ready_row = await repo.mark_ready(
        row,
        session_payload={"expiresAt": int(ready_expires_at.timestamp())},
        expires_at=ready_expires_at,
    )
    assert ready_row is row
    assert row.status == "ready"
    assert row.session_payload == {"expiresAt": int(ready_expires_at.timestamp())}
    assert row.expires_at == ready_expires_at

    await repo.mark_failed(row, status="delivery_failed")
    assert row.status == "delivery_failed"
    paid_row = await repo.mark_paid(row)
    assert paid_row is row
    assert row.status == "paid"
    assert fake_session.flush.await_count == 4

    fake_session.execute.return_value = _FakeScalarResult(row)
    assert await repo.get_by_external_reference_id("ref-123") is row
    assert await repo.get_by_token(token) is row


@pytest.mark.asyncio
async def test_toast_checkout_session_repository_claims_processing_session() -> None:
    row = cast(
        ToastCheckoutSession,
        SimpleNamespace(status="processing", external_reference_id="ref-123"),
    )
    fake_session = SimpleNamespace(
        execute=AsyncMock(return_value=_FakeScalarResult(row))
    )
    repo = ToastCheckoutSessionRepository(cast(AsyncSession, fake_session))

    assert await repo.claim_processing_by_external_reference_id("ref-123") is row


@pytest.mark.asyncio
async def test_toast_checkout_session_repository_rolls_back_create_errors() -> None:
    fake_session = SimpleNamespace(
        add=MagicMock(),
        flush=AsyncMock(side_effect=SQLAlchemyError("flush failed")),
        rollback=AsyncMock(),
    )
    repo = ToastCheckoutSessionRepository(cast(AsyncSession, fake_session))

    with pytest.raises(SQLAlchemyError):
        await repo.create(
            token=uuid.uuid4(),
            conversation_id=uuid.uuid4(),
            external_reference_id="ref-123",
            order_external_id="ORDER-123",
            request_payload={},
            session_payload={},
            checkout_url="https://checkout.test",
            expires_at=datetime.now(timezone.utc),
        )

    fake_session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_toast_checkout_session_repository_rolls_back_update_errors() -> None:
    fake_session = SimpleNamespace(
        flush=AsyncMock(side_effect=SQLAlchemyError("flush failed")),
        rollback=AsyncMock(),
    )
    repo = ToastCheckoutSessionRepository(cast(AsyncSession, fake_session))
    row = cast(
        ToastCheckoutSession,
        SimpleNamespace(status="processing", session_payload={}, expires_at=None),
    )

    with pytest.raises(SQLAlchemyError):
        await repo.mark_ready(
            row,
            session_payload={"expiresAt": 1},
            expires_at=datetime.now(timezone.utc),
        )
    with pytest.raises(SQLAlchemyError):
        await repo.mark_failed(row, status="delivery_failed")
    with pytest.raises(SQLAlchemyError):
        await repo.mark_paid(row)

    assert fake_session.rollback.await_count == 3


@pytest.mark.asyncio
async def test_toast_checkout_session_repository_rolls_back_claim_errors() -> None:
    fake_session = SimpleNamespace(
        execute=AsyncMock(side_effect=SQLAlchemyError("update failed")),
        rollback=AsyncMock(),
    )
    repo = ToastCheckoutSessionRepository(cast(AsyncSession, fake_session))

    with pytest.raises(SQLAlchemyError):
        await repo.claim_processing_by_external_reference_id("ref-123")

    fake_session.rollback.assert_awaited_once()
