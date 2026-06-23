from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.exc import SQLAlchemyError

import services.transaction_service as transaction_service
from services.transaction_service import _implementation

PAYMENT_REFERENCE_ID = "8f2ddc2f-25fd-4c55-943f-04162c43e571"


class FakeAsyncSessionLocal:
    def __init__(self) -> None:
        self.commits: list[str] = []

    async def __aenter__(self) -> FakeAsyncSessionLocal:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None

    async def commit(self) -> None:
        self.commits.append("commit")


@pytest.mark.asyncio
async def test_get_toast_checkout_session_snapshot_returns_detached_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkout_session = SimpleNamespace(
        status="ready",
        session_payload={"storeId": "toast-store"},
        order_external_id="PALONA:test-session",
    )

    class FakeRepository:
        def __init__(self, _session: FakeAsyncSessionLocal) -> None:
            return

        async def get_by_external_reference_id(self, external_reference_id: str) -> Any:
            assert external_reference_id == PAYMENT_REFERENCE_ID
            return checkout_session

    monkeypatch.setattr(_implementation, "AsyncSessionLocal", FakeAsyncSessionLocal)
    monkeypatch.setattr(
        _implementation, "ToastCheckoutSessionRepository", FakeRepository
    )

    result = await transaction_service.get_toast_checkout_session_snapshot(
        PAYMENT_REFERENCE_ID
    )

    assert result == ("ready", {"storeId": "toast-store"}, "PALONA:test-session")
    assert result[1] is not checkout_session.session_payload


@pytest.mark.asyncio
async def test_get_toast_checkout_session_snapshot_returns_empty_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeRepository:
        def __init__(self, _session: FakeAsyncSessionLocal) -> None:
            return

        async def get_by_external_reference_id(
            self, external_reference_id: str
        ) -> None:
            assert external_reference_id == PAYMENT_REFERENCE_ID
            return None

    monkeypatch.setattr(_implementation, "AsyncSessionLocal", FakeAsyncSessionLocal)
    monkeypatch.setattr(
        _implementation, "ToastCheckoutSessionRepository", FakeRepository
    )

    result = await transaction_service.get_toast_checkout_session_snapshot(
        PAYMENT_REFERENCE_ID
    )

    assert result == (None, {}, None)


@pytest.mark.asyncio
async def test_claim_toast_checkout_session_processing_commits_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sessions: list[FakeAsyncSessionLocal] = []

    class CapturingAsyncSessionLocal(FakeAsyncSessionLocal):
        def __init__(self) -> None:
            super().__init__()
            sessions.append(self)

    class FakeRepository:
        def __init__(self, _session: FakeAsyncSessionLocal) -> None:
            return

        async def claim_processing_by_external_reference_id(
            self, external_reference_id: str
        ) -> Any:
            assert external_reference_id == PAYMENT_REFERENCE_ID
            return SimpleNamespace(status="processing")

        async def get_by_external_reference_id(
            self, _external_reference_id: str
        ) -> Any:
            raise AssertionError("claimed session should not be fetched again")

    monkeypatch.setattr(
        _implementation, "AsyncSessionLocal", CapturingAsyncSessionLocal
    )
    monkeypatch.setattr(
        _implementation, "ToastCheckoutSessionRepository", FakeRepository
    )

    result = await transaction_service.claim_toast_checkout_session_processing(
        PAYMENT_REFERENCE_ID
    )

    assert result == "claimed"
    assert sessions[0].commits == ["commit"]


@pytest.mark.asyncio
async def test_claim_toast_checkout_session_processing_returns_existing_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeRepository:
        def __init__(self, _session: FakeAsyncSessionLocal) -> None:
            return

        async def claim_processing_by_external_reference_id(
            self, external_reference_id: str
        ) -> None:
            assert external_reference_id == PAYMENT_REFERENCE_ID
            return None

        async def get_by_external_reference_id(self, external_reference_id: str) -> Any:
            assert external_reference_id == PAYMENT_REFERENCE_ID
            return SimpleNamespace(status="processing")

    monkeypatch.setattr(_implementation, "AsyncSessionLocal", FakeAsyncSessionLocal)
    monkeypatch.setattr(
        _implementation, "ToastCheckoutSessionRepository", FakeRepository
    )

    result = await transaction_service.claim_toast_checkout_session_processing(
        PAYMENT_REFERENCE_ID
    )

    assert result == "processing"


@pytest.mark.asyncio
async def test_mark_toast_checkout_session_paid_commits_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sessions: list[FakeAsyncSessionLocal] = []
    checkout_session = SimpleNamespace(status="processing")

    class CapturingAsyncSessionLocal(FakeAsyncSessionLocal):
        def __init__(self) -> None:
            super().__init__()
            sessions.append(self)

    class FakeRepository:
        def __init__(self, _session: FakeAsyncSessionLocal) -> None:
            return

        async def get_by_external_reference_id(self, external_reference_id: str) -> Any:
            assert external_reference_id == PAYMENT_REFERENCE_ID
            return checkout_session

        async def mark_paid(self, row: Any) -> Any:
            row.status = "paid"
            return row

    monkeypatch.setattr(
        _implementation, "AsyncSessionLocal", CapturingAsyncSessionLocal
    )
    monkeypatch.setattr(
        _implementation, "ToastCheckoutSessionRepository", FakeRepository
    )

    await transaction_service.mark_toast_checkout_session_paid(PAYMENT_REFERENCE_ID)

    assert checkout_session.status == "paid"
    assert sessions[0].commits == ["commit"]


@pytest.mark.asyncio
async def test_mark_toast_checkout_session_paid_swallows_db_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeRepository:
        def __init__(self, _session: FakeAsyncSessionLocal) -> None:
            return

        async def get_by_external_reference_id(self, external_reference_id: str) -> Any:
            assert external_reference_id == PAYMENT_REFERENCE_ID
            return SimpleNamespace(status="processing")

        async def mark_paid(self, _row: Any) -> Any:
            raise SQLAlchemyError("db unavailable")

    monkeypatch.setattr(_implementation, "AsyncSessionLocal", FakeAsyncSessionLocal)
    monkeypatch.setattr(
        _implementation, "ToastCheckoutSessionRepository", FakeRepository
    )

    await transaction_service.mark_toast_checkout_session_paid(PAYMENT_REFERENCE_ID)
