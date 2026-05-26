import asyncio
import re
import sys
import uuid
from contextlib import asynccontextmanager
from importlib import import_module
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.schemas.chat.message import AuthorType, Message, Metadata, TextObject
from db.tables.types import Channel
from utils.request_context import RequestContext


def _ensure_package_module(
    monkeypatch: pytest.MonkeyPatch, name: str, module: ModuleType | None = None
) -> ModuleType:
    pkg = module or ModuleType(name)
    # Mark as package so nested imports behave predictably.
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


def _install_agent_shims_if_needed(monkeypatch: pytest.MonkeyPatch) -> None:
    try:
        import agent  # noqa: F401

        return
    except Exception:
        pass

    agent_mod = ModuleType("agent")
    framework_mod = ModuleType("agent.framework")
    framework_internal_mod = ModuleType("agent.framework.internal")
    input_output_mod = ModuleType("agent.input_output")
    storage_mod = ModuleType("agent.storage")
    storage_impl_mod = ModuleType("agent.storage._implementation")
    _ensure_package_module(monkeypatch, "agent", agent_mod)
    _ensure_package_module(monkeypatch, "agent.framework", framework_mod)
    _ensure_package_module(
        monkeypatch, "agent.framework.internal", framework_internal_mod
    )
    _ensure_package_module(monkeypatch, "agent.storage", storage_mod)
    monkeypatch.setitem(sys.modules, "agent.input_output", input_output_mod)
    monkeypatch.setitem(sys.modules, "agent.storage._implementation", storage_impl_mod)

    class _NoopAgent:
        def __init__(self, config):
            self.config = config

        async def arun(self, _input):
            async def _stream():
                if False:
                    yield None

            return _stream()

    class _Output:
        def __init__(self, content="", closing_conversation=False):
            self.content = content
            self.closing_conversation = closing_conversation

    class _Input:
        def __init__(self, content="", stream=False):
            self.content = content
            self.stream = stream

    async def _query_history_messages(*args, **kwargs):
        return []

    agent_mod.Agent = _NoopAgent  # type: ignore[attr-defined]
    input_output_mod.Input = _Input  # type: ignore[attr-defined]
    input_output_mod.Output = _Output  # type: ignore[attr-defined]
    storage_impl_mod.query_history_messages = _query_history_messages  # type: ignore[attr-defined]


def _install_services_shims_if_needed(monkeypatch: pytest.MonkeyPatch) -> None:
    real_services_pkg = import_module("services")
    _ensure_package_module(monkeypatch, "services", real_services_pkg)
    agent_service_mod = ModuleType("services.agent_service")
    project_service_mod = ModuleType("services.project_service")
    user_service_mod = ModuleType("services.user_service")
    monkeypatch.setitem(sys.modules, "services.agent_service", agent_service_mod)
    monkeypatch.setitem(sys.modules, "services.project_service", project_service_mod)
    monkeypatch.setitem(sys.modules, "services.user_service", user_service_mod)

    async def _not_implemented(*args, **kwargs):
        raise NotImplementedError

    agent_service_mod.construct_agent_config = _not_implemented  # type: ignore[attr-defined]
    agent_service_mod.construct_agent_spec = _not_implemented  # type: ignore[attr-defined]
    project_service_mod.get_project_async = _not_implemented  # type: ignore[attr-defined]
    user_service_mod.get_user_async = _not_implemented  # type: ignore[attr-defined]
    user_service_mod.create_user_async = _not_implemented  # type: ignore[attr-defined]


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


class _FakeAgent:
    def __init__(self, config):
        self.config = config

    async def arun(self, _input):
        async def _stream():
            yield "hello"
            yield " world"

        return _stream()


class _FakeAgentRepo:
    async def get_agent(self, agent_id):
        return SimpleNamespace(language=None)


@pytest.mark.asyncio
async def test_get_chat_response_stream_generates_chatcmpl_stream_id_and_reuses_it(
    monkeypatch,
):
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_agent_shims_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)
    from services.message_service import _implementation

    entered_blocks: list[str] = []
    message_repo = _FakeMessageRepo()
    agent_repo = _FakeAgentRepo()

    @asynccontextmanager
    async def _fake_trace_async_block(name, resource=None, service=None, tags=None):
        entered_blocks.append(name)
        yield None

    user = SimpleNamespace(id=uuid.uuid4())
    project = SimpleNamespace(
        id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        raw_config={"use_pal_agents": False},
        agent_id=uuid.uuid4(),
        account=SimpleNamespace(name="test-account"),
        agent=SimpleNamespace(),
        timezone="America/Los_Angeles",
        name="test-project",
    )

    async def _fake_get_project_async(session, message):
        return project

    async def _fake_get_user_async(session, project, message):
        return user, False

    async def _fake_construct_agent_config(**kwargs):
        return SimpleNamespace(stream=False)

    async def _fake_get_agent_input_from_message(**kwargs):
        return {"input": "ok"}

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
        "construct_agent_config",
        _fake_construct_agent_config,
    )
    monkeypatch.setattr(
        _implementation._utils,
        "get_agent_input_from_message",
        _fake_get_agent_input_from_message,
    )
    monkeypatch.setattr(_implementation, "Agent", _FakeAgent)

    session = AsyncMock()
    message = Message(
        author_type=AuthorType.USER,
        sender_identifier="+15550001111",
        recipient_identifier="+15550002222",
        channel=Channel.SMS,
        text=TextObject(body="Can you help me?"),
        metadata=Metadata(testing=True),
    )

    chunks = [
        chunk
        async for chunk in _implementation.get_chat_response_stream(
            session=session,
            message=message,
            request_context=RequestContext(),
        )
    ]

    assert "Message Service Stream Processing" in entered_blocks
    assert len(chunks) == 2

    stream_ids = {chunk.id for chunk in chunks}
    assert len(stream_ids) == 1
    stream_id = chunks[0].id
    assert stream_id.startswith("chatcmpl-")
    assert re.fullmatch(r"chatcmpl-[0-9a-f]{32}", stream_id)
    assert all(chunk.choices[0].index == 0 for chunk in chunks)


@pytest.mark.asyncio
async def test_get_chat_response_stream_passes_context_fields_to_runtime_context(
    monkeypatch,
):
    """Verify channel, room_name, and participant_identity are forwarded to RuntimeContext."""
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_agent_shims_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)
    from services.message_service import _implementation

    entered_blocks: list[str] = []
    message_repo = _FakeMessageRepo()
    agent_repo = _FakeAgentRepo()

    @asynccontextmanager
    async def _fake_trace_async_block(name, resource=None, service=None, tags=None):
        entered_blocks.append(name)
        yield None

    user = SimpleNamespace(id=uuid.uuid4())
    project = SimpleNamespace(
        id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        raw_config={"use_pal_agents": True},
        agent_id=uuid.uuid4(),
        account=SimpleNamespace(name="test-account"),
        agent=SimpleNamespace(filler_words=None),
        timezone="America/Los_Angeles",
        name="test-project",
    )

    async def _fake_get_project_async(session, message):
        return project

    async def _fake_get_user_async(session, project, message):
        return user, False

    async def _fake_construct_agent_spec(**kwargs):
        return SimpleNamespace()

    # Capture the PalInput passed to pal_agent.run() so we can inspect runtime_context
    captured_inputs: list = []

    class _CapturingPalAgent:
        def __init__(self, spec=None):
            self.spec = spec

        async def run(self, pal_input, stream=False):
            captured_inputs.append(pal_input)

            async def _stream():
                yield SimpleNamespace(content="hello")
                yield SimpleNamespace(content=" world")

            return _stream()

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
    monkeypatch.setattr(_implementation, "PalAgent", _CapturingPalAgent)

    async def _fake_query_history_messages(*args, **kwargs):
        return []

    monkeypatch.setattr(
        _implementation, "query_history_messages", _fake_query_history_messages
    )
    monkeypatch.setattr(_implementation, "record_duration", lambda *a, **kw: None)

    session = AsyncMock()
    message = Message(
        author_type=AuthorType.USER,
        sender_identifier="+15550001111",
        recipient_identifier="+15550002222",
        channel=Channel.VOICE,
        text=TextObject(body="Hello there"),
        metadata=Metadata(testing=True),
    )

    room_name = "room-abc-123"
    participant_identity = "participant-xyz-456"

    chunks = [
        chunk
        async for chunk in _implementation.get_chat_response_stream(
            session=session,
            message=message,
            request_context=RequestContext(),
            call_id=None,
            room_name=room_name,
            participant_identity=participant_identity,
        )
    ]

    # Verify chunks were produced (2 content chunks + 1 finish chunk)
    assert len(chunks) >= 2

    # Verify RuntimeContext received the correct fields
    assert len(captured_inputs) == 1
    rc = captured_inputs[0].runtime_context
    assert rc.channel == "voice"
    assert rc.room_name == room_name
    assert rc.participant_identity == participant_identity


@pytest.mark.asyncio
async def test_get_chat_response_stream_pal_agents_none_stream_ends_cleanly(
    monkeypatch,
):
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_agent_shims_if_needed(monkeypatch)
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
        timezone="America/Los_Angeles",
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

    class _NoneStreamPalAgent:
        def __init__(self, spec=None):
            self.spec = spec

        async def run(self, pal_input, stream=False):
            return None

    async def _fake_query_history_messages(*args, **kwargs):
        return []

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
    monkeypatch.setattr(_implementation, "PalAgent", _NoneStreamPalAgent)
    monkeypatch.setattr(
        _implementation, "query_history_messages", _fake_query_history_messages
    )
    monkeypatch.setattr(_implementation, "record_duration", lambda *a, **kw: None)

    session = AsyncMock()
    message = Message(
        author_type=AuthorType.USER,
        sender_identifier="+15550001111",
        recipient_identifier="+15550002222",
        channel=Channel.VOICE,
        text=TextObject(body="Hello there"),
        metadata=Metadata(testing=True),
    )

    chunks = [
        chunk
        async for chunk in _implementation.get_chat_response_stream(
            session=session,
            message=message,
            request_context=RequestContext(),
        )
    ]

    assert chunks == []


@pytest.mark.asyncio
async def test_get_chat_response_stream_pal_agents_non_async_stream_yields_error_chunk(
    monkeypatch,
):
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_agent_shims_if_needed(monkeypatch)
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
        timezone="America/Los_Angeles",
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

    class _InvalidStreamPalAgent:
        def __init__(self, spec=None):
            self.spec = spec

        async def run(self, pal_input, stream=False):
            return object()

    async def _fake_query_history_messages(*args, **kwargs):
        return []

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
    monkeypatch.setattr(_implementation, "PalAgent", _InvalidStreamPalAgent)
    monkeypatch.setattr(
        _implementation, "query_history_messages", _fake_query_history_messages
    )
    monkeypatch.setattr(_implementation, "record_duration", lambda *a, **kw: None)

    session = AsyncMock()
    message = Message(
        author_type=AuthorType.USER,
        sender_identifier="+15550001111",
        recipient_identifier="+15550002222",
        channel=Channel.VOICE,
        text=TextObject(body="Hello there"),
        metadata=Metadata(testing=True),
    )

    chunks = [
        chunk
        async for chunk in _implementation.get_chat_response_stream(
            session=session,
            message=message,
            request_context=RequestContext(),
        )
    ]

    assert len(chunks) == 1
    assert chunks[0].choices[0].finish_reason == "stop"


@pytest.mark.asyncio
async def test_get_chat_response_stream_pal_agents_iteration_cancelled_ends_cleanly(
    monkeypatch,
):
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_agent_shims_if_needed(monkeypatch)
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
        timezone="America/Los_Angeles",
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

    class _CancelledPalAgent:
        def __init__(self, spec=None):
            self.spec = spec

        async def run(self, pal_input, stream=False):
            async def _stream():
                if False:
                    yield None
                raise asyncio.CancelledError()

            return _stream()

    async def _fake_query_history_messages(*args, **kwargs):
        return []

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
    monkeypatch.setattr(_implementation, "PalAgent", _CancelledPalAgent)
    monkeypatch.setattr(
        _implementation, "query_history_messages", _fake_query_history_messages
    )
    monkeypatch.setattr(_implementation, "record_duration", lambda *a, **kw: None)

    session = AsyncMock()
    message = Message(
        author_type=AuthorType.USER,
        sender_identifier="+15550001111",
        recipient_identifier="+15550002222",
        channel=Channel.VOICE,
        text=TextObject(body="Hello there"),
        metadata=Metadata(testing=True),
    )

    chunks = [
        chunk
        async for chunk in _implementation.get_chat_response_stream(
            session=session,
            message=message,
            request_context=RequestContext(),
        )
    ]

    assert chunks == []


@pytest.mark.asyncio
async def test_get_chat_response_stream_outer_cancelled_error_returns_cleanly(
    monkeypatch,
):
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_agent_shims_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)
    from services.message_service import _implementation

    @asynccontextmanager
    async def _fake_trace_async_block(name, resource=None, service=None, tags=None):
        yield None

    async def _cancelled_get_project_async(session, message):
        raise asyncio.CancelledError()

    monkeypatch.setattr(_implementation, "trace_async_block", _fake_trace_async_block)
    monkeypatch.setattr(
        _implementation.project_service,
        "get_project_async",
        _cancelled_get_project_async,
    )

    session = AsyncMock()
    message = Message(
        author_type=AuthorType.USER,
        sender_identifier="+15550001111",
        recipient_identifier="+15550002222",
        channel=Channel.VOICE,
        text=TextObject(body="Hello there"),
        metadata=Metadata(testing=True),
    )

    chunks = [
        chunk
        async for chunk in _implementation.get_chat_response_stream(
            session=session,
            message=message,
            request_context=RequestContext(),
        )
    ]

    assert chunks == []


@pytest.mark.asyncio
async def test_get_chat_response_stream_legacy_agent_closing_conversation_updates_status(
    monkeypatch,
):
    """Test that closing_conversation flag triggers conversation status update in legacy agent path."""
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_agent_shims_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)
    from services.message_service import _implementation

    entered_blocks: list[str] = []
    message_repo = _FakeMessageRepo()
    agent_repo = _FakeAgentRepo()

    @asynccontextmanager
    async def _fake_trace_async_block(name, resource=None, service=None, tags=None):
        entered_blocks.append(name)
        yield None

    user = SimpleNamespace(id=uuid.uuid4())
    project = SimpleNamespace(
        id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        raw_config={"use_pal_agents": False},
        agent_id=uuid.uuid4(),
        account=SimpleNamespace(name="test-account"),
        agent=SimpleNamespace(),
        timezone="America/Los_Angeles",
        name="test-project",
    )

    async def _fake_get_project_async(session, message):
        return project

    async def _fake_get_user_async(session, project, message):
        return user, False

    async def _fake_construct_agent_config(**kwargs):
        return SimpleNamespace(stream=False)

    async def _fake_get_agent_input_from_message(**kwargs):
        return {"input": "ok"}

    # Create an Agent that yields a chunk with closing_conversation=True
    class _ClosingAgent:
        def __init__(self, config):
            self.config = config

        async def arun(self, _input):
            async def _stream():
                # Import Output from agent.input_output to match implementation
                from agent.input_output import Output

                yield Output(content="goodbye", closing_conversation=True)

            return _stream()

    # Track calls to ConversationRepositoryAsync
    conversation_repo_calls = []
    fake_conversation = SimpleNamespace(status=None)

    class _FakeConversationRepo:
        def __init__(self, session):
            self.session = session

        async def get_conversation_by_id(self, conversation_id):
            conversation_repo_calls.append(conversation_id)
            return fake_conversation

    monkeypatch.setattr(_implementation, "trace_async_block", _fake_trace_async_block)
    monkeypatch.setattr(
        _implementation.db, "MessageRepositoryAsync", lambda session: message_repo
    )
    monkeypatch.setattr(
        _implementation.db, "AgentRepositoryAsync", lambda session: agent_repo
    )
    monkeypatch.setattr(
        _implementation.db,
        "ConversationRepositoryAsync",
        _FakeConversationRepo,
    )
    monkeypatch.setattr(
        _implementation.project_service, "get_project_async", _fake_get_project_async
    )
    monkeypatch.setattr(
        _implementation.user_service, "get_user_async", _fake_get_user_async
    )
    monkeypatch.setattr(
        _implementation.agent_service,
        "construct_agent_config",
        _fake_construct_agent_config,
    )
    monkeypatch.setattr(
        _implementation._utils,
        "get_agent_input_from_message",
        _fake_get_agent_input_from_message,
    )
    monkeypatch.setattr(_implementation, "Agent", _ClosingAgent)

    # Mock ConversationStatus enum
    class _FakeConversationStatus:
        CLOSING = "closing"

    monkeypatch.setattr(
        _implementation.db, "ConversationStatus", _FakeConversationStatus
    )

    session = AsyncMock()
    message = Message(
        author_type=AuthorType.USER,
        sender_identifier="+15550001111",
        recipient_identifier="+15550002222",
        channel=Channel.SMS,
        text=TextObject(body="goodbye"),
        metadata=Metadata(testing=True),
    )

    chunks = [
        chunk
        async for chunk in _implementation.get_chat_response_stream(
            session=session,
            message=message,
            request_context=RequestContext(),
        )
    ]

    # Verify conversation repository was called
    assert len(conversation_repo_calls) == 1
    # Verify conversation status was updated
    assert fake_conversation.status == "closing"
    # Verify session.flush was called
    assert session.flush.called
    # Verify chunks were produced
    assert len(chunks) >= 1


@pytest.mark.asyncio
async def test_get_chat_response_stream_wires_store_status_into_runtime_context(
    monkeypatch,
):
    """compute_store_status output is attached to the RuntimeContext (streaming)."""
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_agent_shims_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)
    from services.message_service import _implementation

    message_repo = _FakeMessageRepo()
    agent_repo = _FakeAgentRepo()

    @asynccontextmanager
    async def _fake_trace_async_block(name, resource=None, service=None, tags=None):
        yield None

    user = SimpleNamespace(id=uuid.uuid4())
    project = SimpleNamespace(
        id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        raw_config={"use_pal_agents": True},
        agent_id=uuid.uuid4(),
        account=SimpleNamespace(name="test-account"),
        agent=SimpleNamespace(filler_words=None),
        timezone="America/Los_Angeles",
        name="test-project",
        # True 24/7: each day's close is the NEXT day's 00:00 (no 23:59 end-of-day
        # gap), so it's open at every instant -> deterministic despite real now.
        business_hours={
            "regular_hours": {
                "periods": [
                    {
                        "open": {"day": d, "time": "0000"},
                        "close": {"day": (d + 1) % 7, "time": "0000"},
                    }
                    for d in range(7)
                ]
            }
        },
        store_hours=None,
    )

    async def _fake_get_project_async(session, message):
        return project

    async def _fake_get_user_async(session, project, message):
        return user, False

    async def _fake_construct_agent_spec(**kwargs):
        return SimpleNamespace()

    captured_inputs: list = []

    class _CapturingPalAgent:
        def __init__(self, spec=None):
            self.spec = spec

        async def run(self, pal_input, stream=False):
            captured_inputs.append(pal_input)

            async def _stream():
                yield SimpleNamespace(content="hello")

            return _stream()

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
    monkeypatch.setattr(_implementation, "PalAgent", _CapturingPalAgent)

    async def _fake_query_history_messages(*args, **kwargs):
        return []

    monkeypatch.setattr(
        _implementation, "query_history_messages", _fake_query_history_messages
    )
    monkeypatch.setattr(_implementation, "record_duration", lambda *a, **kw: None)

    session = AsyncMock()
    message = Message(
        author_type=AuthorType.USER,
        sender_identifier="+15550001111",
        recipient_identifier="+15550002222",
        channel=Channel.VOICE,
        text=TextObject(body="Hello there"),
        metadata=Metadata(testing=True),
    )

    _chunks = [
        chunk
        async for chunk in _implementation.get_chat_response_stream(
            session=session,
            message=message,
            request_context=RequestContext(),
            call_id=None,
        )
    ]

    assert len(captured_inputs) == 1
    store_status = captured_inputs[0].runtime_context.store_status
    assert store_status["status"] == "open"
    assert store_status["is_open"] is True
    assert store_status["source"] == "business_hours"
