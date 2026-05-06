"""Test catering_details persistence from streaming and non-streaming paths."""

import datetime
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
    reservation_service_mod.save_reservation_from_agent_async = _not_implemented  # type: ignore[attr-defined]
    catering_service_mod.create_catering_request_async = _not_implemented  # type: ignore[attr-defined]


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

        async def run(self, pal_input, stream=False):
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
    assert catering["event_fulfillment"] == "DELIVERY"
    assert catering["idempotency_key"] is not None


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

        async def run(self, pal_input, stream=False):
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

        async def run(self, pal_input, stream=False):
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
    assert catering["event_fulfillment"] == "DELIVERY"
    assert catering["idempotency_key"] is not None
