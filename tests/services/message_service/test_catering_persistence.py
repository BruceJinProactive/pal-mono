"""Test catering_details persistence from streaming and non-streaming paths."""

import datetime
import sys
import uuid
from contextlib import asynccontextmanager
from types import ModuleType, SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.schemas.chat.message import AuthorType, Message, Metadata, TextObject
from db.pal_repository.data_classes.catering_request import CateringRequestData
from db.tables.types import Channel
from utils.request_context import RequestContext


def _catering_request_data(
    *,
    request_id: uuid.UUID,
    event_date: datetime.date | None,
    event_time: datetime.time | None = None,
    all_items: dict[str, dict[str, Any]] | None = None,
) -> CateringRequestData:
    now = datetime.datetime(2026, 6, 9, tzinfo=datetime.UTC)
    return CateringRequestData(
        id=request_id,
        project_id=uuid.uuid4(),
        event_date=event_date,
        contact_name="John Doe",
        contact_phone_number="+15551234567",
        contact_email="john@example.com",
        status="LEAD",
        idempotency_key=str(request_id),
        created_at=now,
        updated_at=now,
        event_time=event_time,
        all_items=all_items,
    )


def test_select_catering_request_for_overwrite_uses_latest_without_time():
    from services.message_service._implementation import (
        _select_catering_request_for_overwrite,
    )

    latest_id = uuid.uuid4()
    older_id = uuid.uuid4()
    requests = [
        _catering_request_data(
            request_id=latest_id,
            event_date=datetime.date(2026, 6, 20),
        ),
        _catering_request_data(
            request_id=older_id,
            event_date=datetime.date(2026, 6, 10),
        ),
    ]

    selected = _select_catering_request_for_overwrite(requests, None)

    assert selected is not None
    assert selected.id == latest_id


def test_select_catering_request_for_overwrite_uses_latest_for_invalid_time():
    from services.message_service._implementation import (
        _select_catering_request_for_overwrite,
    )

    latest_id = uuid.uuid4()
    requests = [
        _catering_request_data(
            request_id=latest_id,
            event_date=datetime.date(2026, 6, 20),
        ),
        _catering_request_data(
            request_id=uuid.uuid4(),
            event_date=datetime.date(2026, 6, 10),
        ),
    ]

    selected = _select_catering_request_for_overwrite(requests, "next Tuesday")

    assert selected is not None
    assert selected.id == latest_id


def test_select_catering_request_for_overwrite_prefers_exact_date_time():
    from services.message_service._implementation import (
        _select_catering_request_for_overwrite,
    )

    selected_id = uuid.uuid4()
    requests = [
        _catering_request_data(
            request_id=uuid.uuid4(),
            event_date=datetime.date(2026, 6, 20),
            event_time=datetime.time(12, 0),
        ),
        _catering_request_data(
            request_id=selected_id,
            event_date=datetime.date(2026, 6, 20),
            event_time=datetime.time(18, 30),
        ),
    ]

    selected = _select_catering_request_for_overwrite(
        requests,
        "2026-06-20 18:30",
    )

    assert selected is not None
    assert selected.id == selected_id


def test_select_catering_request_for_overwrite_uses_closest_valid_date():
    from services.message_service._implementation import (
        _select_catering_request_for_overwrite,
    )

    closest_id = uuid.uuid4()
    requests = [
        _catering_request_data(
            request_id=uuid.uuid4(),
            event_date=datetime.date(2026, 6, 1),
        ),
        _catering_request_data(
            request_id=closest_id,
            event_date=datetime.date(2026, 6, 18),
        ),
    ]

    selected = _select_catering_request_for_overwrite(requests, "2026-06-20")

    assert selected is not None
    assert selected.id == closest_id


def test_select_catering_request_for_overwrite_uses_closest_valid_date_time():
    from services.message_service._implementation import (
        _select_catering_request_for_overwrite,
    )

    closest_id = uuid.uuid4()
    requests = [
        _catering_request_data(
            request_id=uuid.uuid4(),
            event_date=datetime.date(2026, 6, 20),
            event_time=datetime.time(8, 0),
        ),
        _catering_request_data(
            request_id=closest_id,
            event_date=datetime.date(2026, 6, 21),
            event_time=datetime.time(17, 0),
        ),
    ]

    selected = _select_catering_request_for_overwrite(
        requests,
        "2026-06-21 18:30",
    )

    assert selected is not None
    assert selected.id == closest_id


def test_serialize_prior_catering_request_includes_expected_fields():
    from services.message_service._implementation import (
        _serialize_prior_catering_request,
    )

    request_id = uuid.uuid4()
    request = _catering_request_data(
        request_id=request_id,
        event_date=datetime.date(2026, 6, 20),
        event_time=datetime.time(18, 30),
        all_items={
            "BBQ Chicken Tray": {
                "quantity": 2,
                "special_notes": "Mild sauce on the side.",
            }
        },
    )

    payload = _serialize_prior_catering_request(request)

    assert payload["id"] == str(request_id)
    assert payload["event_date"] == "2026-06-20"
    assert payload["event_time"] == "18:30:00"
    assert payload["contact_phone_number"] == "+15551234567"
    assert payload["contact_email"] == "john@example.com"
    assert payload["all_items"] == request.all_items


@pytest.mark.asyncio
async def test_attach_prior_catering_requests_to_spec_sets_serialized_requests(
    monkeypatch: pytest.MonkeyPatch,
):
    from services.message_service import _implementation

    request = _catering_request_data(
        request_id=uuid.uuid4(),
        event_date=datetime.date(2026, 6, 20),
    )
    repo = AsyncMock()
    repo.list_by_project_id_and_phone.return_value = [request]
    monkeypatch.setattr(
        _implementation,
        "CateringRequestRepositoryNew",
        lambda session: repo,
    )
    spec = SimpleNamespace(catering_enabled=True)
    project_id = uuid.uuid4()

    await _implementation._attach_prior_catering_requests_to_spec(
        AsyncMock(),
        cast(Any, spec),
        project_id,
        "+15551234567",
    )

    repo.list_by_project_id_and_phone.assert_awaited_once_with(
        project_id,
        "+15551234567",
    )
    assert spec.prior_catering_requests[0]["id"] == str(request.id)


def test_parse_catering_overwrite_time_handles_empty_and_invalid_date_only():
    from services.message_service._implementation import _parse_catering_overwrite_time

    assert _parse_catering_overwrite_time(None) == (None, None)
    assert _parse_catering_overwrite_time("not-a-date") == (None, None)


def test_select_catering_request_for_overwrite_returns_none_without_requests():
    from services.message_service._implementation import (
        _select_catering_request_for_overwrite,
    )

    assert _select_catering_request_for_overwrite([], "2026-06-20") is None


def test_select_catering_request_for_overwrite_ignores_null_dates_for_distance():
    from services.message_service._implementation import (
        _select_catering_request_for_overwrite,
    )

    closest_id = uuid.uuid4()
    requests = [
        _catering_request_data(
            request_id=uuid.uuid4(),
            event_date=None,
        ),
        _catering_request_data(
            request_id=closest_id,
            event_date=datetime.date(2026, 6, 18),
        ),
    ]

    selected = _select_catering_request_for_overwrite(requests, "2026-06-20")

    assert selected is not None
    assert selected.id == closest_id


def test_select_catering_request_for_overwrite_returns_first_when_all_dates_missing() -> (
    None
):
    from services.message_service._implementation import (
        _select_catering_request_for_overwrite,
    )

    first_id = uuid.uuid4()
    requests = [
        _catering_request_data(
            request_id=first_id,
            event_date=None,
        ),
        _catering_request_data(
            request_id=uuid.uuid4(),
            event_date=None,
        ),
    ]

    selected = _select_catering_request_for_overwrite(requests, "2026-06-20")

    assert selected is not None
    assert selected.id == first_id


def test_catering_distance_helpers_treat_null_event_dates_as_unmatchable() -> None:
    from services.message_service._implementation import (
        _catering_event_date_distance,
        _catering_event_datetime_distance,
    )

    request = _catering_request_data(request_id=uuid.uuid4(), event_date=None)

    assert _catering_event_datetime_distance(
        request,
        datetime.datetime(2026, 6, 20, 18, 30),
    ) == float("inf")
    assert _catering_event_date_distance(request, datetime.date(2026, 6, 20)) == 999999


def test_parse_agent_catering_event_date_returns_none_for_invalid_values() -> None:
    from services.message_service._implementation import (
        _parse_agent_catering_event_date,
    )

    assert _parse_agent_catering_event_date("next Tuesday") is None


@pytest.mark.asyncio
async def test_persist_catering_details_from_agent_updates_existing_request(
    monkeypatch: pytest.MonkeyPatch,
):
    from services.message_service import _implementation

    existing_request = _catering_request_data(
        request_id=uuid.uuid4(),
        event_date=datetime.date(2026, 6, 20),
    )
    repo = AsyncMock()
    repo.list_by_project_id_and_phone.return_value = [existing_request]
    monkeypatch.setattr(
        _implementation,
        "CateringRequestRepositoryNew",
        lambda session: repo,
    )
    update_catering_request = AsyncMock()
    create_catering_request_async = AsyncMock()
    monkeypatch.setattr(
        _implementation.catering_service,
        "update_catering_request",
        update_catering_request,
    )
    monkeypatch.setattr(
        _implementation.catering_service,
        "create_catering_request_async",
        create_catering_request_async,
    )

    cd = SimpleNamespace(
        event_date="2026-06-21",
        contact_name="John Doe",
        contact_phone_number="+15551234567",
        contact_email="lead@example.com",
        party_size=30,
        event_time=None,
        event_address="123 Main St",
        event_detail="Pizza",
        event_fulfillment="DELIVERY",
        overwrite=True,
        overwrite_time=None,
    )

    await _implementation._persist_catering_details_from_agent(
        session=AsyncMock(),
        project_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        cd=cd,
    )

    update_catering_request.assert_awaited_once()
    update_args = update_catering_request.await_args
    assert update_args is not None
    assert update_args.kwargs["catering_request_id"] == existing_request.id
    assert update_args.kwargs["contact_email"] == "lead@example.com"
    create_catering_request_async.assert_not_called()


@pytest.mark.asyncio
async def test_persist_catering_details_from_agent_creates_partial_request(
    monkeypatch: pytest.MonkeyPatch,
):
    from services.message_service import _implementation

    create_catering_request_async = AsyncMock()
    monkeypatch.setattr(
        _implementation.catering_service,
        "create_catering_request_async",
        create_catering_request_async,
    )

    cd = SimpleNamespace(
        event_date=None,
        contact_name="Email Lead",
        contact_phone_number=None,
        contact_email="lead@example.com",
        party_size=30,
        event_time=None,
        event_address="123 Main St",
        event_detail="Pizza",
        event_fulfillment=None,
        overwrite=False,
    )
    conversation_id = uuid.uuid4()

    await _implementation._persist_catering_details_from_agent(
        session=AsyncMock(),
        project_id=uuid.uuid4(),
        conversation_id=conversation_id,
        cd=cd,
        activity_source=_implementation._get_catering_request_activity_source_for_channel(
            Channel.EMAIL
        ),
    )

    create_catering_request_async.assert_awaited_once()
    await_args = create_catering_request_async.await_args
    assert await_args is not None
    kwargs = await_args.kwargs
    assert kwargs["event_date"] is None
    assert kwargs["contact_phone_number"] is None
    assert kwargs["contact_email"] == "lead@example.com"
    assert kwargs["idempotency_key"] == str(conversation_id)
    assert kwargs["activity_source"].value == "CUSTOMER_EMAIL"


@pytest.mark.parametrize(
    ("channel", "expected_source"),
    [
        (Channel.INTERNAL_APP, "INTERNAL_APP"),
        (Channel.API, "API"),
        (None, "AI_AGENT"),
    ],
)
def test_get_catering_request_activity_source_for_channel_maps_remaining_sources(
    channel: Channel | None,
    expected_source: str,
) -> None:
    from services.message_service import _implementation

    source = _implementation._get_catering_request_activity_source_for_channel(channel)

    assert source.value == expected_source


def _ensure_package_module(
    monkeypatch: pytest.MonkeyPatch, name: str, module: ModuleType | None = None
) -> ModuleType:
    pkg = module or ModuleType(name)
    if not hasattr(pkg, "__path__"):
        pkg.__path__ = []  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, name, pkg)
    return pkg


def _install_knowledge_shim_if_needed(monkeypatch: pytest.MonkeyPatch) -> None:
    try:
        import pal_agents.providers.knowledge  # noqa: F401

        return
    except Exception:
        pass

    from importlib import import_module

    pal_agents_importable = True
    try:
        pal_agents_pkg = import_module("pal_agents")
    except Exception:
        pal_agents_importable = False
        pal_agents_pkg = ModuleType("pal_agents")
    _ensure_package_module(monkeypatch, "pal_agents", pal_agents_pkg)

    try:
        providers_pkg = import_module("pal_agents.providers")
    except Exception:
        providers_pkg = ModuleType("pal_agents.providers")
    _ensure_package_module(monkeypatch, "pal_agents.providers", providers_pkg)

    if not pal_agents_importable:
        input_mod = ModuleType("pal_agents.input")
        _ensure_package_module(monkeypatch, "pal_agents.input", input_mod)

        class _NoopPalAgent:
            def __init__(self, spec=None):
                self.spec = spec

            async def run(
                self,
                _input: object,
                stream: bool = False,
                **_kwargs: Any,
            ) -> object:
                async def _stream():
                    if False:
                        yield None

                return _stream()

        class _NoopPalInput:
            def __init__(self, content="", runtime_context=None):
                self.content = content
                self.runtime_context = runtime_context

        class _NoopRuntimeContext:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

        pal_agents_pkg.Agent = _NoopPalAgent  # type: ignore[attr-defined]
        pal_agents_pkg.Input = _NoopPalInput  # type: ignore[attr-defined]
        input_mod.RuntimeContext = _NoopRuntimeContext  # type: ignore[attr-defined]

    knowledge_mod = ModuleType("pal_agents.providers.knowledge")
    monkeypatch.setitem(sys.modules, "pal_agents.providers.knowledge", knowledge_mod)

    class _NoopKnowledge:
        def __init__(self, *_args, **_kwargs):
            return

        async def as_text_async(self) -> str | None:
            return None

        def as_tool(self):
            return None

    knowledge_mod.Knowledge = _NoopKnowledge  # type: ignore[attr-defined]


def _install_services_shims_if_needed(monkeypatch: pytest.MonkeyPatch) -> None:
    from importlib import import_module

    real_services_pkg = import_module("services")
    _ensure_package_module(monkeypatch, "services", real_services_pkg)
    agent_service_mod = ModuleType("services.agent_service")
    project_service_mod = ModuleType("services.project_service")
    user_service_mod = ModuleType("services.user_service")
    transaction_service_mod = ModuleType("services.transaction_service")
    reservation_service_mod = ModuleType("services.reservation_service")
    catering_service_mod = ModuleType("services.catering_service")
    monkeypatch.setitem(sys.modules, "services.agent_service", agent_service_mod)
    monkeypatch.setitem(sys.modules, "services.project_service", project_service_mod)
    monkeypatch.setitem(sys.modules, "services.user_service", user_service_mod)
    monkeypatch.setitem(
        sys.modules, "services.transaction_service", transaction_service_mod
    )
    monkeypatch.setitem(
        sys.modules, "services.reservation_service", reservation_service_mod
    )
    monkeypatch.setitem(sys.modules, "services.catering_service", catering_service_mod)

    async def _not_implemented(*args, **kwargs):
        raise NotImplementedError

    agent_service_mod.construct_agent_config = _not_implemented  # type: ignore[attr-defined]
    agent_service_mod.construct_agent_spec = _not_implemented  # type: ignore[attr-defined]
    project_service_mod.get_project_async = _not_implemented  # type: ignore[attr-defined]
    user_service_mod.get_user_async = _not_implemented  # type: ignore[attr-defined]
    user_service_mod.create_user_async = _not_implemented  # type: ignore[attr-defined]
    transaction_service_mod.create_order_from_agent_async = _not_implemented  # type: ignore[attr-defined]
    transaction_service_mod.save_order = _not_implemented  # type: ignore[attr-defined]
    transaction_service_mod.get_order_by_order_id_store_vendor = _not_implemented  # type: ignore[attr-defined]
    reservation_service_mod.save_reservation_from_agent_async = _not_implemented  # type: ignore[attr-defined]
    reservation_service_mod.save_reservation = _not_implemented  # type: ignore[attr-defined]
    reservation_service_mod.save_waitlist = _not_implemented  # type: ignore[attr-defined]
    catering_service_mod.create_catering_request = _not_implemented  # type: ignore[attr-defined]
    catering_service_mod.create_catering_request_async = _not_implemented  # type: ignore[attr-defined]
    catering_service_mod.update_catering_request = _not_implemented  # type: ignore[attr-defined]
    catering_service_mod.send_sms_notification = _not_implemented  # type: ignore[attr-defined]


@pytest.fixture(autouse=True)
def _message_service_dependency_shims(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)


class _FakeMessageRepo:
    def __init__(self):
        self.saved_conversation_id = None
        self.saved_message_body = None

    async def create_message(self, **kwargs):
        self.created_message_kwargs = kwargs
        return SimpleNamespace(conversation_id=uuid.uuid4())

    async def add_message_to_conversation(self, conversation_id, message_body):
        self.saved_conversation_id = conversation_id
        self.saved_message_body = message_body


class _FakeAgentRepo:
    async def get_agent(self, agent_id):
        return SimpleNamespace(language=None)


@pytest.mark.asyncio
async def test_catering_details_persisted_from_stream(monkeypatch):
    """catering_details from a streaming chunk are persisted via catering_service."""
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)
    from services.message_service import _implementation

    message_repo = _FakeMessageRepo()
    agent_repo = _FakeAgentRepo()
    user = SimpleNamespace(id=uuid.uuid4())
    project_id = uuid.uuid4()
    project = SimpleNamespace(
        id=project_id,
        account_id=uuid.uuid4(),
        raw_config={"use_pal_agents": True},
        agent_id=uuid.uuid4(),
        account=SimpleNamespace(name="test-account"),
        agent=SimpleNamespace(filler_words=None),
        timezone="America/Chicago",
        name="test-project",
    )

    @asynccontextmanager
    async def _fake_trace_async_block(name, resource=None, service=None, tags=None):
        yield None

    async def _fake_get_project_async(session, message):
        return project

    async def _fake_get_user_async(session, project, message):
        return user, False

    async def _fake_construct_agent_spec(**kwargs):
        return SimpleNamespace()

    class _CateringStreamPalAgent:
        def __init__(self, spec=None):
            self.spec = spec

        async def run(
            self,
            pal_input: object,
            stream: bool = False,
            **_kwargs: Any,
        ) -> object:
            async def _stream():
                yield SimpleNamespace(
                    content="Your catering request has been submitted!"
                )

                catering_details = SimpleNamespace(
                    event_date="2025-12-25",
                    contact_name="John Doe",
                    contact_phone_number="+15551234567",
                    party_size=30,
                    event_time="14:30",
                    event_address="123 Main St",
                    event_detail="50 pepperoni pizzas",
                    all_items={"Pepperoni pizza": {"quantity": 50, "price": 500.00}},
                    event_fulfillment="DELIVERY",
                )
                yield SimpleNamespace(content="", catering_details=catering_details)

            return _stream()

    async def _fake_query_history_messages(*args, **kwargs):
        return []

    fake_sync_session = MagicMock()
    fake_session = AsyncMock()
    fake_session.sync_session = fake_sync_session
    fake_session.commit = AsyncMock()
    fake_session.rollback = AsyncMock()

    async def _fake_run_sync(func):
        func(fake_sync_session)

    fake_session.run_sync = _fake_run_sync

    persisted_catering: list[dict] = []

    async def _fake_create_catering_request_async(**kwargs):
        persisted_catering.append(kwargs)
        return SimpleNamespace(id=uuid.uuid4())

    monkeypatch.setattr(_implementation, "trace_async_block", _fake_trace_async_block)
    monkeypatch.setattr(
        _implementation.db, "MessageRepositoryAsync", lambda session: message_repo
    )
    monkeypatch.setattr(
        _implementation.db, "AgentRepositoryAsync", lambda session: agent_repo
    )
    monkeypatch.setattr(
        _implementation.project_service, "get_project_async", _fake_get_project_async
    )
    monkeypatch.setattr(
        _implementation.user_service, "get_user_async", _fake_get_user_async
    )
    monkeypatch.setattr(
        _implementation.agent_service,
        "construct_agent_spec",
        _fake_construct_agent_spec,
    )
    monkeypatch.setattr(_implementation, "PalAgent", _CateringStreamPalAgent)
    monkeypatch.setattr(
        _implementation, "query_history_messages", _fake_query_history_messages
    )
    monkeypatch.setattr(_implementation, "record_duration", lambda *a, **kw: None)
    monkeypatch.setattr(
        _implementation.reservation_service,
        "save_reservation_from_agent_async",
        AsyncMock(),
    )
    monkeypatch.setattr(
        _implementation.catering_service,
        "create_catering_request_async",
        _fake_create_catering_request_async,
    )

    message = Message(
        author_type=AuthorType.USER,
        sender_identifier="+15550001111",
        recipient_identifier="+15550002222",
        channel=Channel.VOICE,
        text=TextObject(body="I'd like to place a catering order for 30 people"),
        metadata=Metadata(testing=True),
    )

    chunks = [
        chunk
        async for chunk in _implementation.get_chat_response_stream(
            session=fake_session,
            message=message,
            request_context=RequestContext(),
        )
    ]

    assert len(chunks) >= 1
    assert (
        chunks[0].choices[0].delta.content
        == "Your catering request has been submitted!"
    )

    assert len(persisted_catering) == 1
    catering = persisted_catering[0]
    assert catering["project_id"] == project_id
    assert catering["event_date"] == datetime.date(2025, 12, 25)
    assert catering["contact_name"] == "John Doe"
    assert catering["contact_phone_number"] == "+15551234567"
    assert catering["party_size"] == 30
    assert catering["event_time"] == datetime.time(14, 30)
    assert catering["event_address"] == "123 Main St"
    assert catering["event_detail"] == "50 pepperoni pizzas"
    assert catering["all_items"] == {
        "Pepperoni pizza": {"quantity": 50, "price": 500.00}
    }
    assert catering["event_fulfillment"] == "DELIVERY"
    assert catering["idempotency_key"] is not None
    assert catering["activity_source"].value == "CUSTOMER_VOICE"


@pytest.mark.asyncio
async def test_catering_details_persisted_without_optional_fields(monkeypatch):
    """catering_details with only required fields are persisted correctly."""
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)
    from services.message_service import _implementation

    message_repo = _FakeMessageRepo()
    agent_repo = _FakeAgentRepo()
    user = SimpleNamespace(id=uuid.uuid4())
    project_id = uuid.uuid4()
    project = SimpleNamespace(
        id=project_id,
        account_id=uuid.uuid4(),
        raw_config={"use_pal_agents": True},
        agent_id=uuid.uuid4(),
        account=SimpleNamespace(name="test-account"),
        agent=SimpleNamespace(filler_words=None),
        timezone="America/Chicago",
        name="test-project",
    )

    @asynccontextmanager
    async def _fake_trace_async_block(name, resource=None, service=None, tags=None):
        yield None

    async def _fake_get_project_async(session, message):
        return project

    async def _fake_get_user_async(session, project, message):
        return user, False

    async def _fake_construct_agent_spec(**kwargs):
        return SimpleNamespace()

    class _CateringStreamPalAgent:
        def __init__(self, spec=None):
            self.spec = spec

        async def run(
            self,
            pal_input: object,
            stream: bool = False,
            **_kwargs: Any,
        ) -> object:
            async def _stream():
                yield SimpleNamespace(content="Catering request received!")

                catering_details = SimpleNamespace(
                    event_date="2025-12-25",
                    contact_name="Jane",
                    contact_phone_number="+15559876543",
                    party_size=10,
                    event_time=None,
                    event_address=None,
                    event_detail=None,
                    event_fulfillment=None,
                )
                yield SimpleNamespace(content="", catering_details=catering_details)

            return _stream()

    async def _fake_query_history_messages(*args, **kwargs):
        return []

    fake_sync_session = MagicMock()
    fake_session = AsyncMock()
    fake_session.sync_session = fake_sync_session
    fake_session.commit = AsyncMock()
    fake_session.rollback = AsyncMock()

    async def _fake_run_sync(func):
        func(fake_sync_session)

    fake_session.run_sync = _fake_run_sync

    persisted_catering: list[dict] = []

    async def _fake_create_catering_request_async(**kwargs):
        persisted_catering.append(kwargs)
        return SimpleNamespace(id=uuid.uuid4())

    monkeypatch.setattr(_implementation, "trace_async_block", _fake_trace_async_block)
    monkeypatch.setattr(
        _implementation.db, "MessageRepositoryAsync", lambda session: message_repo
    )
    monkeypatch.setattr(
        _implementation.db, "AgentRepositoryAsync", lambda session: agent_repo
    )
    monkeypatch.setattr(
        _implementation.project_service, "get_project_async", _fake_get_project_async
    )
    monkeypatch.setattr(
        _implementation.user_service, "get_user_async", _fake_get_user_async
    )
    monkeypatch.setattr(
        _implementation.agent_service,
        "construct_agent_spec",
        _fake_construct_agent_spec,
    )
    monkeypatch.setattr(_implementation, "PalAgent", _CateringStreamPalAgent)
    monkeypatch.setattr(
        _implementation, "query_history_messages", _fake_query_history_messages
    )
    monkeypatch.setattr(_implementation, "record_duration", lambda *a, **kw: None)
    monkeypatch.setattr(
        _implementation.reservation_service,
        "save_reservation_from_agent_async",
        AsyncMock(),
    )
    monkeypatch.setattr(
        _implementation.catering_service,
        "create_catering_request_async",
        _fake_create_catering_request_async,
    )

    message = Message(
        author_type=AuthorType.USER,
        sender_identifier="+15550001111",
        recipient_identifier="+15550002222",
        channel=Channel.VOICE,
        text=TextObject(body="Catering for 10"),
        metadata=Metadata(testing=True),
    )

    chunks = [
        chunk
        async for chunk in _implementation.get_chat_response_stream(
            session=fake_session,
            message=message,
            request_context=RequestContext(),
        )
    ]

    assert len(chunks) >= 1

    assert len(persisted_catering) == 1
    catering = persisted_catering[0]
    assert catering["project_id"] == project_id
    assert catering["event_date"] == datetime.date(2025, 12, 25)
    assert catering["contact_name"] == "Jane"
    assert catering["party_size"] == 10
    assert catering["event_time"] is None
    assert catering["event_address"] is None
    assert catering["event_fulfillment"] is None
    assert catering["idempotency_key"] is not None
    assert catering["activity_source"].value == "CUSTOMER_VOICE"


@pytest.mark.asyncio
async def test_catering_details_persisted_from_non_streaming(monkeypatch):
    """catering_details from non-streaming get_chat_response_async are persisted."""
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)
    from services.message_service import _implementation

    message_repo = _FakeMessageRepo()
    agent_repo = _FakeAgentRepo()
    user = SimpleNamespace(id=uuid.uuid4())
    project_id = uuid.uuid4()
    project = SimpleNamespace(
        id=project_id,
        account_id=uuid.uuid4(),
        raw_config={"use_pal_agents": True},
        agent_id=uuid.uuid4(),
        account=SimpleNamespace(name="test-account"),
        agent=SimpleNamespace(filler_words=None),
        timezone="America/Chicago",
        name="test-project",
    )

    async def _fake_get_project_async(session, message):
        return project

    async def _fake_get_user_async(session, project, message):
        return user, False

    async def _fake_construct_agent_spec(**kwargs):
        return SimpleNamespace()

    class _CateringPalAgent:
        def __init__(self, spec=None):
            self.spec = spec

        async def run(
            self,
            pal_input: object,
            stream: bool = False,
            **_kwargs: Any,
        ) -> object:
            return SimpleNamespace(
                content="Your catering request is confirmed!",
                escalated=False,
                closing_conversation=False,
                catering_details=SimpleNamespace(
                    event_date="2025-12-25",
                    contact_name="John Doe",
                    contact_phone_number="+15551234567",
                    party_size=30,
                    event_time="14:30",
                    event_address="123 Main St",
                    event_detail="50 pepperoni pizzas",
                    all_items={"Pepperoni pizza": {"quantity": 50, "price": 500.00}},
                    event_fulfillment="DELIVERY",
                ),
            )

    async def _fake_query_history_messages(*args, **kwargs):
        return []

    fake_session = AsyncMock()
    fake_session.refresh = AsyncMock()

    persisted_catering: list[dict] = []

    async def _fake_create_catering_request_async(**kwargs):
        persisted_catering.append(kwargs)
        return SimpleNamespace(id=uuid.uuid4())

    monkeypatch.setattr(
        _implementation.db, "MessageRepositoryAsync", lambda session: message_repo
    )
    monkeypatch.setattr(
        _implementation.db, "AgentRepositoryAsync", lambda session: agent_repo
    )
    monkeypatch.setattr(
        _implementation.project_service, "get_project_async", _fake_get_project_async
    )
    monkeypatch.setattr(
        _implementation.user_service, "get_user_async", _fake_get_user_async
    )
    monkeypatch.setattr(
        _implementation.agent_service,
        "construct_agent_spec",
        _fake_construct_agent_spec,
    )
    monkeypatch.setattr(_implementation, "PalAgent", _CateringPalAgent)
    monkeypatch.setattr(
        _implementation, "query_history_messages", _fake_query_history_messages
    )
    monkeypatch.setattr(_implementation, "record_duration", lambda *a, **kw: None)
    monkeypatch.setattr(
        _implementation.catering_service,
        "create_catering_request_async",
        _fake_create_catering_request_async,
    )

    message = Message(
        author_type=AuthorType.USER,
        sender_identifier="+15550001111",
        recipient_identifier="+15550002222",
        channel=Channel.SMS,
        text=TextObject(body="Catering for 30 on Christmas"),
        metadata=Metadata(testing=True),
    )

    result = await _implementation.get_chat_response_async(
        session=fake_session,
        message=message,
        request_context=RequestContext(),
    )

    assert len(result) > 0

    assert len(persisted_catering) == 1
    catering = persisted_catering[0]
    assert catering["project_id"] == project_id
    assert catering["event_date"] == datetime.date(2025, 12, 25)
    assert catering["contact_name"] == "John Doe"
    assert catering["contact_phone_number"] == "+15551234567"
    assert catering["party_size"] == 30
    assert catering["event_time"] == datetime.time(14, 30)
    assert catering["event_address"] == "123 Main St"
    assert catering["event_detail"] == "50 pepperoni pizzas"
    assert catering["all_items"] == {
        "Pepperoni pizza": {"quantity": 50, "price": 500.00}
    }
    assert catering["event_fulfillment"] == "DELIVERY"
    assert catering["idempotency_key"] is not None
    assert catering["activity_source"].value == "CUSTOMER_SMS"
