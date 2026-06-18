from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import MissingGreenlet
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.chat.message import Broker


def test_format_payment_amount() -> None:
    from services.toast_checkout_service import _implementation as service

    assert service._format_payment_amount(0) == "$0.00"
    assert service._format_payment_amount(1) == "$0.01"
    assert service._format_payment_amount(2418) == "$24.18"


def test_format_order_summary_caps_visible_items() -> None:
    from services.toast_checkout_service import _implementation as service

    summary = service._format_order_summary(
        [
            {"name": "Pizza", "quantity": 1},
            {"name": "Coke", "quantity": 2},
            {"name": "Fries", "quantity": 1},
            {"name": "Cookie", "quantity": 3},
        ]
    )

    assert summary == "Pizza x1, Coke x2, Fries x1, +1 more"


def test_format_order_summary_normalizes_item_fallbacks() -> None:
    from services.toast_checkout_service import _implementation as service

    summary = service._format_order_summary(
        [
            {"name": "Smoothie", "quantity": 1.0},
            {"item_name": "Cookie", "quantity": 1.5},
            {"displayName": "Tea", "quantity": " 2 "},
            {"name": "  ", "quantity": None},
            {"name": "Water", "quantity": True},
        ],
        max_items=5,
    )

    assert summary == "Smoothie x1, Cookie x1.5, Tea x2, Item x1, Water x1"


def test_build_payment_sms_uses_store_name_without_order_summary() -> None:
    from services.toast_checkout_service import _implementation as service

    checkout_url = "https://payment.palona.link/abc123"
    payload = service.ToastCheckoutPayload(
        amount_cents=2418,
        external_reference_id="external-reference",
        order_external_id="order-external",
        customer_email="customer@example.com",
        customer_name="Customer",
        customer_phone="+15551234567",
        order_items=[
            {"name": "A" * 5000, "quantity": 2},
            {"name": "B" * 5000, "quantity": 1},
            {"name": "C" * 5000, "quantity": 1},
        ],
        subtotal_cents=2200,
        tax_cents=218,
        store_id="store-id",
        store_name="Toast Store",
    )

    sms = service._build_payment_sms(
        sender_identifier="+15550000000",
        recipient_identifier="+15551234567",
        checkout_url=checkout_url,
        payload=payload,
    )

    assert sms.text is not None
    assert sms.text.body == (
        "Your order at Toast Store is ready for payment.\n\n"
        "Total: $24.18\n"
        "Order summary is available on the payment page:\n"
        f"{checkout_url}"
    )
    assert "Order summary: " not in sms.text.body
    assert "Pay here" not in sms.text.body
    assert "AAAA" not in sms.text.body


def test_build_payment_sms_falls_back_to_restaurant_name() -> None:
    from services.toast_checkout_service import _implementation as service

    checkout_url = "https://payment.palona.link/abc123"
    payload = service.ToastCheckoutPayload(
        amount_cents=2418,
        external_reference_id="external-reference",
        order_external_id="order-external",
        customer_email="customer@example.com",
        customer_name="Customer",
        customer_phone="+15551234567",
        order_items=[{"name": "Pizza", "quantity": 1}],
        subtotal_cents=2200,
        tax_cents=218,
        store_id="store-id",
    )

    sms = service._build_payment_sms(
        sender_identifier="+15550000000",
        recipient_identifier="+15551234567",
        checkout_url=checkout_url,
        payload=payload,
    )

    assert sms.text is not None
    assert sms.text.body == (
        "Your order is ready for payment.\n\n"
        "Total: $24.18\n"
        "Order summary is available on the payment page:\n"
        f"{checkout_url}"
    )


@pytest.mark.asyncio
async def test_build_checkout_url_uses_env_url_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.toast_checkout_service import _implementation as service

    calls: list[tuple[str, bool]] = []

    def _fake_shorten_url(url: str, *, use_env_url_prefix: bool = False) -> str:
        calls.append((url, use_env_url_prefix))
        return "https://tiny.test/checkout"

    monkeypatch.setattr(service, "shorten_url", _fake_shorten_url)

    result = await service._build_checkout_url_async(
        uuid.UUID("3080391c-538c-44a7-9063-bcec4ded5676")
    )

    assert result == "https://tiny.test/checkout"
    assert calls == [
        (
            "https://console.palona.ai/checkout/toast?"
            "t=3080391c-538c-44a7-9063-bcec4ded5676",
            True,
        )
    ]


class _ExpiringCheckoutSession:
    def __init__(self, **kwargs: Any) -> None:
        object.__setattr__(self, "_expired", False)
        for key, value in kwargs.items():
            object.__setattr__(self, key, value)

    def expire(self) -> None:
        object.__setattr__(self, "_expired", True)

    def refresh(self) -> None:
        object.__setattr__(self, "_expired", False)

    def __getattribute__(self, name: str) -> Any:
        if name.startswith("_") or name in {"expire", "refresh"}:
            return object.__getattribute__(self, name)
        if object.__getattribute__(self, "_expired"):
            raise MissingGreenlet("expired attribute requires async refresh")
        return object.__getattribute__(self, name)

    def __setattr__(self, name: str, value: Any) -> None:
        object.__setattr__(self, name, value)


@pytest.mark.asyncio
async def test_process_checkout_request_creates_session_and_sends_sms(monkeypatch):
    from services.toast_checkout_service import _implementation as service

    stored_sessions: list[Any] = []
    sent_messages: list[Any] = []
    created_payment_intents: list[Any] = []
    tracking_updates: list[dict[str, Any]] = []
    sessions_by_reference: dict[str, SimpleNamespace] = {}

    class FakeSessionRepository:
        def __init__(self, _session):
            return

        async def get_by_external_reference_id(self, external_reference_id):
            return sessions_by_reference.get(external_reference_id)

        async def create(
            self,
            *,
            token,
            conversation_id,
            external_reference_id,
            order_external_id,
            request_payload,
            session_payload,
            checkout_url,
            expires_at,
            status,
        ):
            row = SimpleNamespace(
                id=uuid.uuid4(),
                token=token,
                conversation_id=conversation_id,
                external_reference_id=external_reference_id,
                order_external_id=order_external_id,
                request_payload=request_payload,
                session_payload=session_payload,
                checkout_url=checkout_url,
                expires_at=expires_at,
                status=status,
            )
            sessions_by_reference[external_reference_id] = row
            stored_sessions.append(row)
            return row

        async def mark_ready(self, row, *, session_payload, expires_at):
            row.session_payload = session_payload
            row.expires_at = expires_at
            row.status = "ready"
            return row

        async def mark_failed(self, row, *, status):
            row.status = status

    monkeypatch.setattr(
        service, "ToastCheckoutSessionRepository", FakeSessionRepository
    )
    monkeypatch.setattr(
        service,
        "get_toast_access_token_from_aws",
        lambda **kwargs: SimpleNamespace(
            access_token=f"token:{kwargs.get('token_name', 'default')}"
        ),
    )
    monkeypatch.setattr(
        service,
        "create_payment_intent",
        lambda **kwargs: created_payment_intents.append(kwargs)
        or SimpleNamespace(
            id="pi_123",
            sessionSecret="session-secret",
            amount=kwargs["payment_request"].amount,
            externalReferenceId=kwargs["payment_request"].externalReferenceId,
        ),
    )
    monkeypatch.setattr(
        service,
        "shorten_url",
        lambda url, *, use_env_url_prefix=False: (
            f"https://tiny.test/{url.rsplit('=', 1)[-1]}"
        ),
    )
    monkeypatch.setattr(
        service,
        "send_message",
        lambda message: sent_messages.append(message) or {"status": "scheduled"},
    )

    async def _fake_update_order_tracking_link_async(*, session, payload, checkout_url):
        tracking_updates.append(
            {
                "order_external_id": payload.order_external_id,
                "store_id": payload.store_id,
                "checkout_url": checkout_url,
            }
        )

    monkeypatch.setattr(
        service,
        "_update_order_tracking_link_async",
        _fake_update_order_tracking_link_async,
    )

    request = {
        "type": "payment_checkout",
        "provider": "toast",
        "payload": {
            "amount_cents": 3500,
            "tip_cents": 0,
            "external_reference_id": "8f2ddc2f-25fd-4c55-943f-04162c43e571",
            "order_external_id": "PALONA:test-session",
            "customer_email": "orderingagent+5145609523@palona.ai",
            "customer_name": "John Doe",
            "customer_phone": "5145609523",
            "order_items": [
                {"name": "Pizza", "quantity": 1, "totalcost": 3000},
                {"name": "Coke", "quantity": 2, "totalcost": 500},
            ],
            "subtotal_cents": 3000,
            "tax_cents": 500,
            "gratuity_fees": [],
            "store_id": "toast-store",
            "store_name": "Toast Store",
        },
    }

    fake_session_obj = SimpleNamespace(commit=AsyncMock())
    fake_session_obj.refresh = AsyncMock()
    fake_session = cast(AsyncSession, fake_session_obj)

    result = await service.process_checkout_request_async(
        session=fake_session,
        checkout_request=request,
        conversation_id=uuid.uuid4(),
        sender_identifier="+15551230000",
        recipient_identifier="+15551234567",
    )

    assert result.checkout_url.startswith("https://tiny.test/")
    assert len(stored_sessions) == 1
    session_payload = stored_sessions[0].session_payload
    assert session_payload == {
        "email": "orderingagent+5145609523@palona.ai",
        "name": "John Doe",
        "phone": "5145609523",
        "storeId": "toast-store",
        "storeName": "Toast Store",
        "orderExternalId": "PALONA:test-session",
        "paymentIntentId": "pi_123",
        "paymentIntentExternalReferenceId": "8f2ddc2f-25fd-4c55-943f-04162c43e571",
        "subtotal": 3000,
        "tax": 500,
        "gratuityFees": [],
        "total": 3500,
        "tips": 0,
        "sessionSecret": "session-secret",
        "iframeBearerToken": "token:TOAST_PAYMENT_IFRAME_ACCESS_TOKEN",
        "orderItems": [
            {"name": "Pizza", "quantity": 1, "totalcost": 3000},
            {"name": "Coke", "quantity": 2, "totalcost": 500},
        ],
        "expiresAt": session_payload["expiresAt"],
    }
    assert isinstance(stored_sessions[0].token, uuid.UUID)
    assert stored_sessions[0].status == "ready"
    assert stored_sessions[0].external_reference_id == (
        "8f2ddc2f-25fd-4c55-943f-04162c43e571"
    )
    assert stored_sessions[0].order_external_id == "PALONA:test-session"
    assert stored_sessions[0].expires_at > datetime.now(timezone.utc)
    assert len(sent_messages) == 1
    assert sent_messages[0].text.body == (
        "Your order at Toast Store is ready for payment.\n\n"
        "Total: $35.00\n"
        "Order summary is available on the payment page:\n"
        f"{result.checkout_url}"
    )
    assert sent_messages[0].recipient_identifier == "+15145609523"
    assert sent_messages[0].broker == Broker.TWILIO
    assert len(created_payment_intents) == 1
    assert tracking_updates == [
        {
            "order_external_id": "PALONA:test-session",
            "store_id": "toast-store",
            "checkout_url": result.checkout_url,
        }
    ]

    duplicate_result = await service.process_checkout_request_async(
        session=fake_session,
        checkout_request=request,
        conversation_id=uuid.uuid4(),
        sender_identifier="+15551230000",
        recipient_identifier="+15550000000",
    )

    assert duplicate_result == result
    assert len(stored_sessions) == 1
    assert len(sent_messages) == 1
    assert len(created_payment_intents) == 1
    assert len(tracking_updates) == 1


@pytest.mark.asyncio
async def test_process_checkout_request_refreshes_session_after_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.toast_checkout_service import _implementation as service

    rows: list[_ExpiringCheckoutSession] = []
    sent_messages: list[Any] = []

    class FakeSessionRepository:
        def __init__(self, _session: object) -> None:
            return

        async def get_by_external_reference_id(
            self, _external_reference_id: str
        ) -> None:
            return None

        async def create(self, **kwargs: Any) -> _ExpiringCheckoutSession:
            row = _ExpiringCheckoutSession(**kwargs)
            rows.append(row)
            return row

        async def mark_ready(
            self,
            row: _ExpiringCheckoutSession,
            *,
            session_payload: dict[str, Any],
            expires_at: datetime,
        ) -> _ExpiringCheckoutSession:
            row.session_payload = session_payload
            row.expires_at = expires_at
            row.status = "ready"
            return row

        async def mark_failed(
            self, row: _ExpiringCheckoutSession, *, status: str
        ) -> None:
            row.status = status

    monkeypatch.setattr(
        service, "ToastCheckoutSessionRepository", FakeSessionRepository
    )
    monkeypatch.setattr(
        service,
        "get_toast_access_token_from_aws",
        lambda **kwargs: SimpleNamespace(
            access_token=f"token:{kwargs.get('token_name')}"
        ),
    )
    monkeypatch.setattr(
        service,
        "create_payment_intent",
        lambda **kwargs: SimpleNamespace(
            id="pi_123",
            sessionSecret="session-secret",
            amount=kwargs["payment_request"].amount,
            externalReferenceId=kwargs["payment_request"].externalReferenceId,
        ),
    )
    monkeypatch.setattr(
        service, "shorten_url", lambda url, *, use_env_url_prefix=False: url
    )
    monkeypatch.setattr(
        service,
        "send_message",
        lambda message: sent_messages.append(message) or {"status": "scheduled"},
    )

    async def _fake_update_order_tracking_link_async(
        *, session: AsyncSession, payload: object, checkout_url: str
    ) -> None:
        return None

    monkeypatch.setattr(
        service,
        "_update_order_tracking_link_async",
        _fake_update_order_tracking_link_async,
    )

    request = {
        "type": "payment_checkout",
        "provider": "toast",
        "payload": {
            "amount_cents": 3500,
            "tip_cents": 0,
            "external_reference_id": "8f2ddc2f-25fd-4c55-943f-04162c43e571",
            "order_external_id": "PALONA:test-session",
            "customer_email": "orderingagent+5551234567@palona.ai",
            "customer_name": "John Doe",
            "customer_phone": "+15551234567",
            "order_items": [],
            "subtotal_cents": 3000,
            "tax_cents": 500,
            "gratuity_fees": [],
            "store_id": "toast-store",
            "store_name": "Toast Store",
        },
    }

    async def _commit() -> None:
        rows[-1].expire()

    async def _refresh(row: _ExpiringCheckoutSession) -> None:
        row.refresh()

    fake_session_obj = SimpleNamespace(commit=AsyncMock(side_effect=_commit))
    fake_session_obj.refresh = AsyncMock(side_effect=_refresh)
    fake_session = cast(AsyncSession, fake_session_obj)

    result = await service.process_checkout_request_async(
        session=fake_session,
        checkout_request=request,
        conversation_id=uuid.uuid4(),
        sender_identifier="+15551230000",
        recipient_identifier="+15551234567",
    )

    assert result.checkout_url.startswith("https://console.palona.ai/checkout/toast")
    assert len(sent_messages) == 1
    assert fake_session_obj.refresh.await_count == 2


@pytest.mark.asyncio
async def test_process_checkout_request_marks_delivery_failure(monkeypatch):
    from services.toast_checkout_service import _implementation as service

    class FakeSessionRepository:
        def __init__(self, _session):
            self.row = getattr(_session, "row", None)

        async def get_by_external_reference_id(self, _external_reference_id):
            return None

        async def create(self, **kwargs):
            self.row = SimpleNamespace(**kwargs)
            return self.row

        async def mark_ready(self, row, *, session_payload, expires_at):
            row.session_payload = session_payload
            row.expires_at = expires_at
            row.status = "ready"
            return row

        async def mark_failed(self, row, *, status):
            row.status = status

    monkeypatch.setattr(
        service, "ToastCheckoutSessionRepository", FakeSessionRepository
    )
    monkeypatch.setattr(
        service,
        "get_toast_access_token_from_aws",
        lambda **kwargs: SimpleNamespace(
            access_token=f"token:{kwargs.get('token_name')}"
        ),
    )
    monkeypatch.setattr(
        service,
        "create_payment_intent",
        lambda **kwargs: SimpleNamespace(
            id="pi_123",
            sessionSecret="session-secret",
            amount=kwargs["payment_request"].amount,
            externalReferenceId=kwargs["payment_request"].externalReferenceId,
        ),
    )
    monkeypatch.setattr(
        service, "shorten_url", lambda url, *, use_env_url_prefix=False: url
    )
    monkeypatch.setattr(
        service,
        "send_message",
        lambda _message: {"status": "error", "error_message": "relay unavailable"},
    )

    async def _fake_update_order_tracking_link_async(*, session, payload, checkout_url):
        return None

    monkeypatch.setattr(
        service,
        "_update_order_tracking_link_async",
        _fake_update_order_tracking_link_async,
    )

    request = {
        "type": "payment_checkout",
        "provider": "toast",
        "payload": {
            "amount_cents": 3500,
            "tip_cents": 0,
            "external_reference_id": "8f2ddc2f-25fd-4c55-943f-04162c43e571",
            "order_external_id": "PALONA:test-session",
            "customer_email": "orderingagent+5551234567@palona.ai",
            "customer_name": "John Doe",
            "customer_phone": "+15551234567",
            "order_items": [],
            "subtotal_cents": 3000,
            "tax_cents": 500,
            "gratuity_fees": [],
            "store_id": "toast-store",
            "store_name": "Toast Store",
        },
    }
    fake_session_obj = SimpleNamespace(commit=AsyncMock())
    fake_session_obj.refresh = AsyncMock()
    fake_session = cast(AsyncSession, fake_session_obj)

    with pytest.raises(service.ToastCheckoutDeliveryError):
        await service.process_checkout_request_async(
            session=fake_session,
            checkout_request=request,
            conversation_id=uuid.uuid4(),
            sender_identifier="+15551230000",
            recipient_identifier="+15551234567",
        )


@pytest.mark.asyncio
async def test_process_checkout_request_retries_delivery_failed_session(monkeypatch):
    from services.toast_checkout_service import _implementation as service

    existing_session = SimpleNamespace(
        token=uuid.uuid4(),
        checkout_url="https://checkout.test/retry",
        status="delivery_failed",
        session_payload={"expiresAt": 9999999999},
        expires_at=datetime.now(timezone.utc),
    )
    sent_messages: list[Any] = []

    class FakeSessionRepository:
        def __init__(self, _session):
            return

        async def get_by_external_reference_id(self, _external_reference_id):
            return existing_session

        async def create(self, **_kwargs):
            raise AssertionError("existing checkout session should be reused")

        async def mark_ready(self, row, *, session_payload, expires_at):
            row.session_payload = session_payload
            row.expires_at = expires_at
            row.status = "ready"
            return row

        async def mark_failed(self, row, *, status):
            row.status = status

    monkeypatch.setattr(
        service, "ToastCheckoutSessionRepository", FakeSessionRepository
    )
    monkeypatch.setattr(
        service,
        "create_payment_intent",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("payment intent should not be recreated")
        ),
    )
    monkeypatch.setattr(
        service,
        "send_message",
        lambda message: sent_messages.append(message) or {"status": "scheduled"},
    )

    request = {
        "type": "payment_checkout",
        "provider": "toast",
        "payload": {
            "amount_cents": 3500,
            "tip_cents": 0,
            "external_reference_id": "8f2ddc2f-25fd-4c55-943f-04162c43e571",
            "order_external_id": "PALONA:test-session",
            "customer_email": "orderingagent+5551234567@palona.ai",
            "customer_name": "John Doe",
            "customer_phone": "+15551234567",
            "order_items": [],
            "subtotal_cents": 3000,
            "tax_cents": 500,
            "gratuity_fees": [],
            "store_id": "toast-store",
            "store_name": "Toast Store",
        },
    }
    fake_session_obj = SimpleNamespace(commit=AsyncMock())
    fake_session_obj.refresh = AsyncMock()
    fake_session = cast(AsyncSession, fake_session_obj)

    result = await service.process_checkout_request_async(
        session=fake_session,
        checkout_request=request,
        conversation_id=uuid.uuid4(),
        sender_identifier="+15551230000",
        recipient_identifier="+15551234567",
    )

    assert result.checkout_url == "https://checkout.test/retry"
    assert existing_session.status == "ready"
    assert len(sent_messages) == 1
    fake_session_obj.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_checkout_session_payload_rejects_expired_session():
    from services.toast_checkout_service import _implementation as service

    expired_payload = {"expiresAt": 1}

    with pytest.raises(service.ToastCheckoutSessionExpiredError):
        service._validate_session_payload(expired_payload)


def test_validate_session_payload_rejects_missing_expiration():
    from services.toast_checkout_service import _implementation as service

    with pytest.raises(service.ToastCheckoutSessionExpiredError):
        service._validate_session_payload({})


def test_select_sms_recipient_normalizes_ten_digit_payload_phone() -> None:
    from services.toast_checkout_service import _implementation as service

    recipient = service._select_sms_recipient(
        preferred_recipient="5145609523",
        fallback_recipient="+15551234567",
    )

    assert recipient == "+15145609523"


def test_select_sms_recipient_preserves_e164_payload_phone() -> None:
    from services.toast_checkout_service import _implementation as service

    recipient = service._select_sms_recipient(
        preferred_recipient="+15145609523",
        fallback_recipient="+15551234567",
    )

    assert recipient == "+15145609523"


def test_select_sms_recipient_falls_back_for_invalid_payload_phone() -> None:
    from services.toast_checkout_service import _implementation as service

    recipient = service._select_sms_recipient(
        preferred_recipient="+1514560",
        fallback_recipient="+15551234567",
    )

    assert recipient == "+15551234567"


@pytest.mark.asyncio
async def test_get_checkout_session_payload_requires_ready_session(monkeypatch):
    from services.toast_checkout_service import _implementation as service

    class FakeSessionRepository:
        def __init__(self, _session):
            return

        async def get_by_token(self, _token):
            return SimpleNamespace(status="delivery_failed", session_payload={})

    monkeypatch.setattr(
        service, "ToastCheckoutSessionRepository", FakeSessionRepository
    )

    with pytest.raises(service.ToastCheckoutSessionNotFoundError):
        await service.get_checkout_session_payload_async(
            cast(AsyncSession, object()), uuid.uuid4()
        )
