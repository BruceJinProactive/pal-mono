from __future__ import annotations

import uuid
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

PAYMENT_REFERENCE_ID = "8f2ddc2f-25fd-4c55-943f-04162c43e571"


@pytest.mark.asyncio
async def test_get_checkout_session_uses_uuid_lookup(monkeypatch):
    from api.routes.integrations.toast import _implementation

    expected_token = uuid.uuid4()
    payload = {"orderExternalId": "PALONA:test", "expiresAt": 9999999999}
    captured: dict = {}

    class FakeAsyncSessionLocal:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return None

    async def _fake_get_checkout_session_payload_async(session, token):
        captured["session"] = session
        captured["token"] = token
        return payload

    monkeypatch.setattr(_implementation, "AsyncSessionLocal", FakeAsyncSessionLocal)
    monkeypatch.setattr(
        _implementation,
        "get_checkout_session_payload_async",
        _fake_get_checkout_session_payload_async,
    )

    response = await _implementation.get_checkout_session(str(expected_token))

    assert response.status_code == 200
    assert captured["token"] == expected_token
    assert response.body


@pytest.mark.asyncio
async def test_get_checkout_session_returns_404_for_missing_uuid(monkeypatch):
    from api.routes.integrations.toast import _implementation

    class FakeAsyncSessionLocal:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return None

    async def _fake_get_checkout_session_payload_async(session, token):
        raise _implementation.ToastCheckoutSessionNotFoundError

    monkeypatch.setattr(_implementation, "AsyncSessionLocal", FakeAsyncSessionLocal)
    monkeypatch.setattr(
        _implementation,
        "get_checkout_session_payload_async",
        _fake_get_checkout_session_payload_async,
    )

    with pytest.raises(HTTPException) as exc_info:
        await _implementation.get_checkout_session(str(uuid.uuid4()))

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_checkout_session_returns_400_for_invalid_uuid():
    from api.routes.integrations.toast import _implementation

    with pytest.raises(HTTPException) as exc_info:
        await _implementation.get_checkout_session("not-a-uuid")

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_get_checkout_session_returns_400_for_expired_session(monkeypatch):
    from api.routes.integrations.toast import _implementation

    class FakeAsyncSessionLocal:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return None

    async def _fake_get_checkout_session_payload_async(session, token):
        raise _implementation.ToastCheckoutSessionExpiredError

    monkeypatch.setattr(_implementation, "AsyncSessionLocal", FakeAsyncSessionLocal)
    monkeypatch.setattr(
        _implementation,
        "get_checkout_session_payload_async",
        _fake_get_checkout_session_payload_async,
    )

    with pytest.raises(HTTPException) as exc_info:
        await _implementation.get_checkout_session(str(uuid.uuid4()))

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_checkout_complete_submits_stored_order_when_toast_order_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from api.routes.integrations.toast import _implementation

    submitted_orders: list[Any] = []
    updated_orders: list[dict[str, Any]] = []

    response = await _call_checkout_complete_for_missing_order(
        monkeypatch,
        session_payload=_valid_session_payload(),
        submit_order=lambda **kwargs: submitted_orders.append(kwargs)
        or SimpleNamespace(guid="submitted-order-guid"),
        update_order=lambda **kwargs: updated_orders.append(kwargs) or True,
    )

    assert response.status_code == 200
    assert len(submitted_orders) == 1
    submitted_order = submitted_orders[0]["order"]
    assert submitted_order.externalId == "PALONA:test-session"
    assert submitted_order.checks[0].payments is not None
    assert submitted_order.checks[0].payments[0].amount == 30
    assert submitted_order.checks[0].payments[0].tipAmount == 5
    assert submitted_order.checks[0].payments[0].guid == PAYMENT_REFERENCE_ID
    assert not hasattr(submitted_order.checks[0].payments[0], "externalId")
    assert updated_orders == [
        {
            "store_id": "toast-store",
            "vendor": _implementation.IntegrationProvider.toast,
            "new_status": "paid",
            "order_id": "PALONA:test-session",
        }
    ]


@pytest.mark.asyncio
async def test_checkout_complete_marks_stored_order_session_paid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    status_updates: list[str] = []

    response = await _call_checkout_complete_for_missing_order(
        monkeypatch,
        session_payload=_valid_session_payload(),
        status_updates=status_updates,
    )

    assert response.status_code == 200
    assert status_updates == ["processing", "paid"]


@pytest.mark.asyncio
async def test_checkout_complete_succeeds_when_paid_marker_update_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    submitted_orders: list[Any] = []

    response = await _call_checkout_complete_for_missing_order(
        monkeypatch,
        session_payload=_valid_session_payload(),
        submit_order=lambda **kwargs: submitted_orders.append(kwargs)
        or SimpleNamespace(guid="submitted-order-guid"),
        mark_paid=lambda _row: (_ for _ in ()).throw(SQLAlchemyError("db unavailable")),
    )

    assert response.status_code == 200
    assert len(submitted_orders) == 1


@pytest.mark.asyncio
async def test_checkout_complete_skips_already_paid_checkout_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = await _call_checkout_complete_for_missing_order(
        monkeypatch,
        session_payload=_valid_session_payload(),
        session_status="paid",
        get_existing_order=lambda *_args, **_kwargs: pytest.fail(
            "paid checkout session should not call Toast"
        ),
        submit_order=lambda **_kwargs: pytest.fail(
            "paid checkout session should not submit order"
        ),
        update_order=lambda **_kwargs: pytest.fail(
            "paid checkout session should not update local order"
        ),
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_checkout_complete_skips_processing_checkout_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = await _call_checkout_complete_for_missing_order(
        monkeypatch,
        session_payload=_valid_session_payload(),
        session_status="processing",
        get_existing_order=lambda *_args, **_kwargs: pytest.fail(
            "processing checkout session should not call Toast"
        ),
        submit_order=lambda **_kwargs: pytest.fail(
            "processing checkout session should not submit order"
        ),
        update_order=lambda **_kwargs: pytest.fail(
            "processing checkout session should not update local order"
        ),
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_checkout_complete_marks_existing_toast_order_session_paid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    status_updates: list[str] = []
    posted_payments: list[Any] = []
    existing_order = SimpleNamespace(
        guid="toast-order-guid",
        checks=[SimpleNamespace(guid="toast-check-guid", totalAmount=30)],
    )

    response = await _call_checkout_complete_for_missing_order(
        monkeypatch,
        session_payload=_valid_session_payload(),
        get_existing_order=lambda *_args, **_kwargs: existing_order,
        post_payment_to_order=lambda **kwargs: posted_payments.append(kwargs),
        status_updates=status_updates,
    )

    assert response.status_code == 200
    assert len(posted_payments) == 1
    assert posted_payments[0]["payment"].externalId == (
        f"TPC-PALONA:{PAYMENT_REFERENCE_ID}"
    )
    assert status_updates == ["processing", "paid"]


@pytest.mark.asyncio
async def test_checkout_complete_rejects_order_external_id_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = await _call_checkout_complete_for_missing_order(
        monkeypatch,
        body_overrides={"orderExternalId": "PALONA:wrong-session"},
        session_payload=_valid_session_payload(),
        get_existing_order=lambda *_args, **_kwargs: pytest.fail(
            "mismatched callback should not call Toast"
        ),
        submit_order=lambda **_kwargs: pytest.fail(
            "mismatched callback should not submit order"
        ),
        update_order=lambda **_kwargs: pytest.fail(
            "mismatched callback should not update local order"
        ),
    )

    assert response.status_code == 400
    assert b"Checkout session does not match callback order" in response.body


@pytest.mark.asyncio
async def test_checkout_complete_rejects_store_id_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = await _call_checkout_complete_for_missing_order(
        monkeypatch,
        body_overrides={"storeId": "wrong-store"},
        session_payload=_valid_session_payload(),
        get_existing_order=lambda *_args, **_kwargs: pytest.fail(
            "mismatched callback should not call Toast"
        ),
        submit_order=lambda **_kwargs: pytest.fail(
            "mismatched callback should not submit order"
        ),
        update_order=lambda **_kwargs: pytest.fail(
            "mismatched callback should not update local order"
        ),
    )

    assert response.status_code == 400
    assert b"Checkout session does not match callback store" in response.body


@pytest.mark.asyncio
async def test_checkout_complete_requires_charged_amount_for_stored_order_submission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = await _call_checkout_complete_for_missing_order(
        monkeypatch,
        body_overrides={"chargedAmountCents": None},
    )

    assert response.status_code == 400
    assert b"chargedAmountCents is required" in response.body


@pytest.mark.asyncio
async def test_checkout_complete_requires_stored_toast_payload_when_order_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = await _call_checkout_complete_for_missing_order(
        monkeypatch,
        session_payload={},
    )

    assert response.status_code == 400
    assert b"cannot add payment to order" in response.body


@pytest.mark.asyncio
async def test_checkout_complete_rejects_invalid_stored_toast_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = await _call_checkout_complete_for_missing_order(
        monkeypatch,
        session_payload={"toastOrderPayload": {"externalId": "PALONA:test-session"}},
    )

    assert response.status_code == 400
    assert b"Stored Toast order payload is invalid" in response.body


@pytest.mark.asyncio
async def test_checkout_complete_rejects_stored_toast_payload_without_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = await _call_checkout_complete_for_missing_order(
        monkeypatch,
        session_payload={
            "toastOrderPayload": {
                "externalId": "PALONA:test-session",
                "diningOption": {"guid": "dining-option-guid"},
                "checks": [],
            }
        },
    )

    assert response.status_code == 400
    assert b"has no checks" in response.body


@pytest.mark.asyncio
async def test_checkout_complete_succeeds_when_local_order_status_update_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    submitted_orders: list[Any] = []

    response = await _call_checkout_complete_for_missing_order(
        monkeypatch,
        session_payload=_valid_session_payload(),
        submit_order=lambda **kwargs: submitted_orders.append(kwargs)
        or SimpleNamespace(guid="submitted-order-guid"),
        update_order=lambda **_kwargs: False,
    )

    assert response.status_code == 200
    assert len(submitted_orders) == 1


def _valid_session_payload() -> dict[str, Any]:
    return {
        "storeId": "toast-store",
        "orderExternalId": "PALONA:test-session",
        "toastOrderPayload": {
            "externalId": "PALONA:test-session",
            "diningOption": {"guid": "dining-option-guid"},
            "checks": [
                {
                    "customer": {
                        "firstName": "John",
                        "phone": "+15551234567",
                        "email": "orderingagent@example.com",
                    },
                    "selections": [
                        {
                            "itemGroup": {"guid": "item-group-guid"},
                            "item": {"guid": "item-guid"},
                            "quantity": 1,
                        }
                    ],
                }
            ],
        },
    }


async def _call_checkout_complete_for_missing_order(
    monkeypatch: pytest.MonkeyPatch,
    *,
    body_overrides: dict[str, Any] | None = None,
    session_payload: dict[str, Any] | None = None,
    session_status: str = "ready",
    submit_order: Callable[..., Any] | None = None,
    get_existing_order: Callable[..., Any] | None = None,
    post_payment_to_order: Callable[..., Any] | None = None,
    update_order: Callable[..., Any] | None = None,
    mark_paid: Callable[[Any], Any] | None = None,
    status_updates: list[str] | None = None,
) -> JSONResponse:
    from api.routes.integrations.toast import _implementation

    body = {
        "storeId": "toast-store",
        "orderExternalId": "PALONA:test-session",
        "paymentExternalReferenceId": PAYMENT_REFERENCE_ID,
        "chargedAmountCents": 3500,
        "tipAmountCents": 500,
    }
    if body_overrides:
        body.update(body_overrides)
    checkout_session = (
        SimpleNamespace(
            session_payload=session_payload,
            status=session_status,
            order_external_id="PALONA:test-session",
        )
        if session_payload is not None
        else None
    )

    class FakeRequest:
        async def json(self) -> dict[str, Any]:
            return body

    async def fake_get_toast_checkout_session_snapshot(
        external_reference_id: str,
    ) -> tuple[str | None, dict[str, Any], str | None]:
        assert external_reference_id == PAYMENT_REFERENCE_ID
        if checkout_session is None:
            return None, {}, None
        return (
            checkout_session.status,
            dict(checkout_session.session_payload),
            checkout_session.order_external_id,
        )

    async def fake_claim_toast_checkout_session_processing(
        external_reference_id: str,
    ) -> str | None:
        assert external_reference_id == PAYMENT_REFERENCE_ID
        if checkout_session is None:
            return None
        if checkout_session.status != "ready":
            return checkout_session.status
        checkout_session.status = "processing"
        if status_updates is not None:
            status_updates.append(checkout_session.status)
        return "claimed"

    async def fake_mark_toast_checkout_session_paid(
        external_reference_id: str,
    ) -> None:
        assert external_reference_id == PAYMENT_REFERENCE_ID
        if checkout_session is None:
            return
        if mark_paid is not None:
            try:
                mark_paid(checkout_session)
            except SQLAlchemyError:
                return
            return
        checkout_session.status = "paid"
        if status_updates is not None:
            status_updates.append(checkout_session.status)

    monkeypatch.setattr(
        _implementation,
        "get_toast_checkout_session_snapshot",
        fake_get_toast_checkout_session_snapshot,
    )
    monkeypatch.setattr(
        _implementation,
        "claim_toast_checkout_session_processing",
        fake_claim_toast_checkout_session_processing,
    )
    monkeypatch.setattr(
        _implementation,
        "mark_toast_checkout_session_paid",
        fake_mark_toast_checkout_session_paid,
    )
    monkeypatch.setattr(
        _implementation,
        "get_toast_access_token_from_aws",
        lambda **_kwargs: SimpleNamespace(access_token="toast-token"),
    )
    monkeypatch.setattr(
        _implementation,
        "get_existing_order",
        get_existing_order or (lambda *_args, **_kwargs: None),
    )
    monkeypatch.setattr(
        _implementation,
        "post_payment_to_order",
        post_payment_to_order or (lambda **_kwargs: None),
    )
    monkeypatch.setattr(
        _implementation,
        "submit_order",
        submit_order
        or (lambda **_kwargs: SimpleNamespace(guid="submitted-order-guid")),
    )
    monkeypatch.setattr(
        _implementation,
        "update_order_by_order_id",
        update_order or (lambda **_kwargs: True),
    )

    return await _implementation.checkout_complete(cast(Request, FakeRequest()))
