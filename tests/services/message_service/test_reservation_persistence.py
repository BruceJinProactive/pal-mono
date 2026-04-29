"""Test reservation_details persistence from streaming chunks."""

import sys
import uuid
from contextlib import asynccontextmanager
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.schemas.chat.message import AuthorType, Message, Metadata, TextObject
from db.tables.types import Channel
from utils.request_context import RequestContext


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

            async def run(self, _input, stream=False):
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
    monkeypatch.setitem(sys.modules, "services.agent_service", agent_service_mod)
    monkeypatch.setitem(sys.modules, "services.project_service", project_service_mod)
    monkeypatch.setitem(sys.modules, "services.user_service", user_service_mod)
    monkeypatch.setitem(
        sys.modules, "services.transaction_service", transaction_service_mod
    )
    monkeypatch.setitem(
        sys.modules, "services.reservation_service", reservation_service_mod
    )

    async def _not_implemented(*args, **kwargs):
        raise NotImplementedError

    agent_service_mod.construct_agent_config = _not_implemented  # type: ignore[attr-defined]
    agent_service_mod.construct_agent_spec = _not_implemented  # type: ignore[attr-defined]
    project_service_mod.get_project_async = _not_implemented  # type: ignore[attr-defined]
    user_service_mod.get_user_async = _not_implemented  # type: ignore[attr-defined]
    user_service_mod.create_user_async = _not_implemented  # type: ignore[attr-defined]
    transaction_service_mod.create_order_from_agent_async = _not_implemented  # type: ignore[attr-defined]
    reservation_service_mod.save_reservation_from_agent_async = _not_implemented  # type: ignore[attr-defined]


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
async def test_reservation_details_persisted_from_stream(monkeypatch):
    """reservation_details from a streaming chunk are persisted via reservation_service."""
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)
    from services.message_service import _implementation

    message_repo = _FakeMessageRepo()
    agent_repo = _FakeAgentRepo()
    user = SimpleNamespace(id=uuid.uuid4())
    project = SimpleNamespace(
        id=uuid.uuid4(),
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

    # PalAgent that yields a chunk with reservation_details
    class _ReservationStreamPalAgent:
        def __init__(self, spec=None):
            self.spec = spec

        async def run(self, pal_input, stream=False):
            async def _stream():
                yield SimpleNamespace(content="Your reservation has been confirmed!")

                reservation_details = SimpleNamespace(
                    vendor="minitable",
                    entry_type="reservation",
                    reservation_id="BOOKING-999",
                    store_id="REST-456",
                    status="confirmed",
                    party_size=4,
                    notes="Window seat",
                    reservation_time="2026-04-10T19:00",
                    arrive_by_time=None,
                    expected_seating_time=None,
                    tracking_link="https://example.com/status/BOOKING-999",
                )
                yield SimpleNamespace(
                    content="", reservation_details=reservation_details
                )

                yield SimpleNamespace(content=" Booking ID: BOOKING-999")

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

    # Track reservation_service calls
    persisted_reservations: list[dict] = []

    async def _fake_save_reservation_from_agent_async(
        session, reservation_details, conversation_id
    ):
        persisted_reservations.append(
            {
                "vendor": reservation_details.vendor,
                "entry_type": reservation_details.entry_type,
                "reservation_id": reservation_details.reservation_id,
                "store_id": reservation_details.store_id,
                "status": reservation_details.status,
                "party_size": reservation_details.party_size,
                "conversation_id": conversation_id,
            }
        )
        return uuid.uuid4()

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
    monkeypatch.setattr(_implementation, "PalAgent", _ReservationStreamPalAgent)
    monkeypatch.setattr(
        _implementation, "query_history_messages", _fake_query_history_messages
    )
    monkeypatch.setattr(_implementation, "record_duration", lambda *a, **kw: None)
    monkeypatch.setattr(
        _implementation.reservation_service,
        "save_reservation_from_agent_async",
        _fake_save_reservation_from_agent_async,
    )

    message = Message(
        author_type=AuthorType.USER,
        sender_identifier="+15550001111",
        recipient_identifier="+15550002222",
        channel=Channel.VOICE,
        text=TextObject(body="I'd like to make a reservation for 4 tonight"),
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

    # Verify chunks were generated
    assert len(chunks) >= 2
    assert chunks[0].choices[0].delta.content == "Your reservation has been confirmed!"

    # Verify reservation was persisted exactly once
    assert len(persisted_reservations) == 1
    reservation = persisted_reservations[0]
    assert reservation["vendor"] == "minitable"
    assert reservation["entry_type"] == "reservation"
    assert reservation["reservation_id"] == "BOOKING-999"
    assert reservation["store_id"] == "REST-456"
    assert reservation["status"] == "confirmed"
    assert reservation["party_size"] == 4


@pytest.mark.asyncio
async def test_reservation_details_error_does_not_break_stream(monkeypatch):
    """Reservation persistence error does not break the streaming response."""
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)
    from services.message_service import _implementation

    message_repo = _FakeMessageRepo()
    agent_repo = _FakeAgentRepo()
    user = SimpleNamespace(id=uuid.uuid4())
    project = SimpleNamespace(
        id=uuid.uuid4(),
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

    class _ReservationStreamPalAgent:
        def __init__(self, spec=None):
            self.spec = spec

        async def run(self, pal_input, stream=False):
            async def _stream():
                reservation_details = SimpleNamespace(
                    vendor="yelp",
                    entry_type="waitlist",
                    reservation_id="VISIT-123",
                    store_id="BIZ-789",
                    status="queued",
                    party_size=2,
                    notes=None,
                    reservation_time=None,
                    arrive_by_time="1700000000",
                    expected_seating_time="1700001800",
                    tracking_link=None,
                )
                yield SimpleNamespace(
                    content="You're on the waitlist!",
                    reservation_details=reservation_details,
                )

            return _stream()

    async def _fake_query_history_messages(*args, **kwargs):
        return []

    # Reservation service that fails
    async def _fake_failing_save(session, reservation_details, conversation_id):
        await session.rollback()
        return None

    fake_sync_session = MagicMock()
    fake_session = AsyncMock()
    fake_session.sync_session = fake_sync_session
    fake_session.commit = AsyncMock()
    fake_session.rollback = AsyncMock()

    async def _fake_run_sync(func):
        func(fake_sync_session)

    fake_session.run_sync = _fake_run_sync

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
    monkeypatch.setattr(_implementation, "PalAgent", _ReservationStreamPalAgent)
    monkeypatch.setattr(
        _implementation, "query_history_messages", _fake_query_history_messages
    )
    monkeypatch.setattr(_implementation, "record_duration", lambda *a, **kw: None)
    monkeypatch.setattr(
        _implementation.reservation_service,
        "save_reservation_from_agent_async",
        _fake_failing_save,
    )

    message = Message(
        author_type=AuthorType.USER,
        sender_identifier="+15550001111",
        recipient_identifier="+15550002222",
        channel=Channel.VOICE,
        text=TextObject(body="Join the waitlist for 2"),
        metadata=Metadata(testing=True),
    )

    # Stream should still produce chunks even when reservation persistence fails
    chunks = [
        chunk
        async for chunk in _implementation.get_chat_response_stream(
            session=fake_session,
            message=message,
            request_context=RequestContext(),
        )
    ]

    assert len(chunks) >= 1
    assert chunks[0].choices[0].delta.content == "You're on the waitlist!"
