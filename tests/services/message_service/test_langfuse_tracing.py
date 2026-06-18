"""Tests verifying Langfuse tracing integration in message_service.

These tests verify that langfuse_message_span is called with the correct
attributes (session_id, user_id, tags, metadata, input/output).
"""

import sys
import uuid
from contextlib import asynccontextmanager, contextmanager
from importlib import import_module
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.schemas.chat.message import AuthorType, Message, Metadata, TextObject
from db.tables.types import Channel
from utils.request_context import RequestContext

# ---------------------------------------------------------------------------
# Shared test infrastructure
# ---------------------------------------------------------------------------


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
                if stream:

                    async def _stream():
                        yield SimpleNamespace(content="streamed")

                    return _stream()
                return SimpleNamespace(
                    content="response", escalated=False, closing_conversation=False
                )

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
    input_output_mod = ModuleType("agent.input_output")
    storage_mod = ModuleType("agent.storage")
    storage_impl_mod = ModuleType("agent.storage._implementation")
    _ensure_package_module(monkeypatch, "agent", agent_mod)
    _ensure_package_module(monkeypatch, "agent.storage", storage_mod)
    monkeypatch.setitem(sys.modules, "agent.input_output", input_output_mod)
    monkeypatch.setitem(sys.modules, "agent.storage._implementation", storage_impl_mod)

    class _NoopAgent:
        def __init__(self, config):
            self.config = config

        async def arun(self, _input):
            return SimpleNamespace(
                content="legacy", escalated=False, closing_conversation=False
            )

    class _Output:
        def __init__(self, content="", closing_conversation=False, escalated=False):
            self.content = content
            self.closing_conversation = closing_conversation
            self.escalated = escalated

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
        self.saved_messages: list[dict] = []

    async def create_message(self, **kwargs):
        return SimpleNamespace(conversation_id=uuid.uuid4())

    async def add_message_to_conversation(self, conversation_id, message_body):
        self.saved_messages.append(
            {"conversation_id": conversation_id, "body": message_body}
        )


class _FakeConversationRepo:
    async def get_conversation_by_id(self, conversation_id):
        return SimpleNamespace(
            id=conversation_id,
            status="active",
            agent_fingerprint=None,
            prompt_fingerprint=None,
            transfer_purpose=None,
            vapi_control_url=None,
        )


def _setup_mocks(monkeypatch, *, use_pal_agents=True):
    """Set up all mocks and return (_implementation, project, user)."""
    from services.message_service import _implementation

    user = SimpleNamespace(id=uuid.uuid4())
    project = SimpleNamespace(
        id=uuid.uuid4(),
        name="test-project",
        account_id=uuid.uuid4(),
        raw_config={"use_pal_agents": use_pal_agents},
        agent_id=uuid.uuid4(),
        timezone="America/Los_Angeles",
        account=SimpleNamespace(name="test-account"),
        agent=SimpleNamespace(filler_words=None),
    )

    message_repo = _FakeMessageRepo()

    async def _fake_get_project_async(session, message):
        return project

    async def _fake_get_user_async(session, proj, message):
        return user, False

    async def _fake_construct_agent_spec(**kwargs):
        return SimpleNamespace()

    async def _fake_construct_agent_config(**kwargs):
        return SimpleNamespace(stream=False)

    async def _fake_get_agent_input(**kwargs):
        return SimpleNamespace(content="input")

    async def _fake_query_history_messages(*args, **kwargs):
        return []

    class _MockPalAgent:
        def __init__(self, spec=None):
            self.spec = spec

        async def run(
            self,
            pal_input: object,
            stream: bool = False,
            **_kwargs: Any,
        ) -> object:
            if stream:

                async def _stream():
                    yield SimpleNamespace(content="streamed")

                return _stream()
            return SimpleNamespace(
                content="response", escalated=False, closing_conversation=False
            )

    class _MockAgent:
        def __init__(self, config):
            self.config = config

        async def arun(self, _input):
            return SimpleNamespace(
                content="legacy", escalated=False, closing_conversation=False
            )

    monkeypatch.setattr(_implementation, "PalAgent", _MockPalAgent)
    monkeypatch.setattr(_implementation, "Agent", _MockAgent)
    monkeypatch.setattr(
        _implementation.db, "MessageRepositoryAsync", lambda session: message_repo
    )
    monkeypatch.setattr(
        _implementation.db,
        "ConversationRepositoryAsync",
        lambda session: _FakeConversationRepo(),
    )
    monkeypatch.setattr(
        _implementation.db, "AgentRepositoryAsync", lambda session: SimpleNamespace()
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
    monkeypatch.setattr(
        _implementation.agent_service,
        "construct_agent_config",
        _fake_construct_agent_config,
    )
    monkeypatch.setattr(
        _implementation._utils, "get_agent_input_from_message", _fake_get_agent_input
    )
    monkeypatch.setattr(
        _implementation, "query_history_messages", _fake_query_history_messages
    )
    monkeypatch.setattr(_implementation, "record_duration", lambda *a, **kw: None)

    return _implementation, project, user


# ---------------------------------------------------------------------------
# Test: langfuse_message_span called with correct args (non-streaming)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_langfuse_span_called_with_correct_args_nonstreaming(monkeypatch):
    """Verify langfuse_message_span receives correct session_id, user_id, tags."""
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_agent_shims_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)

    _impl, project, user = _setup_mocks(monkeypatch, use_pal_agents=True)

    # Capture langfuse_message_span calls
    captured_kwargs: list[dict] = []

    @contextmanager
    def _mock_langfuse_span(**kwargs):
        captured_kwargs.append(kwargs)
        mock_lf = MagicMock()
        yield mock_lf

    monkeypatch.setattr(_impl, "langfuse_message_span", _mock_langfuse_span)

    session = AsyncMock()
    session.refresh = AsyncMock()
    message = Message(
        author_type=AuthorType.USER,
        sender_identifier="+15550001111",
        recipient_identifier="+15550002222",
        channel=Channel.SMS,
        text=TextObject(body="Hello"),
        metadata=Metadata(testing=True),
    )

    await _impl.get_chat_response_async(
        session=session, message=message, request_context=RequestContext()
    )

    # Verify langfuse_message_span was called exactly once
    assert len(captured_kwargs) == 1
    kwargs = captured_kwargs[0]

    # Verify key attributes
    assert kwargs["user_id"] == user.id
    assert kwargs["agent_id"] == project.agent_id
    assert kwargs["account_name"] == "test-account"
    assert kwargs["project_name"] == "test-project"
    assert kwargs["channel"] == "sms"
    # conversation_id is a UUID (from create_message)
    assert isinstance(kwargs["conversation_id"], uuid.UUID)


# ---------------------------------------------------------------------------
# Test: langfuse trace IO captures input and output (non-streaming)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_langfuse_trace_io_set_nonstreaming(monkeypatch):
    """Verify set_current_trace_io is called with input and output."""
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_agent_shims_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)

    _impl, project, user = _setup_mocks(monkeypatch, use_pal_agents=True)

    mock_lf = MagicMock()
    trace_io_calls: list[dict] = []

    def _capture_trace_io(**kwargs):
        trace_io_calls.append(kwargs)

    mock_lf.set_current_trace_io = _capture_trace_io

    @contextmanager
    def _mock_langfuse_span(**kwargs):
        yield mock_lf

    monkeypatch.setattr(_impl, "langfuse_message_span", _mock_langfuse_span)

    session = AsyncMock()
    session.refresh = AsyncMock()
    message = Message(
        author_type=AuthorType.USER,
        sender_identifier="+15550001111",
        recipient_identifier="+15550002222",
        channel=Channel.SMS,
        text=TextObject(body="What is your menu?"),
        metadata=Metadata(testing=True),
    )

    await _impl.get_chat_response_async(
        session=session, message=message, request_context=RequestContext()
    )

    # Should have been called twice: once for input, once for output
    assert len(trace_io_calls) == 2

    # First call: input
    assert trace_io_calls[0] == {"input": {"content": "What is your menu?"}}

    # Second call: output
    assert "output" in trace_io_calls[1]
    assert "content" in trace_io_calls[1]["output"]
    assert trace_io_calls[1]["output"]["content"] == "response"


# ---------------------------------------------------------------------------
# Test: langfuse_message_span called in streaming path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_langfuse_span_called_in_streaming_path(monkeypatch):
    """Verify langfuse_message_span is invoked during streaming."""
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_agent_shims_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)

    _impl, project, user = _setup_mocks(monkeypatch, use_pal_agents=True)

    @asynccontextmanager
    async def _fake_trace_async_block(name, resource=None, service=None, tags=None):
        yield None

    monkeypatch.setattr(_impl, "trace_async_block", _fake_trace_async_block)

    captured_kwargs: list[dict] = []
    mock_lf = MagicMock()
    trace_io_calls: list[dict] = []
    mock_lf.set_current_trace_io = lambda **kw: trace_io_calls.append(kw)

    @contextmanager
    def _mock_langfuse_span(**kwargs):
        captured_kwargs.append(kwargs)
        yield mock_lf

    monkeypatch.setattr(_impl, "langfuse_message_span", _mock_langfuse_span)

    session = AsyncMock()
    session.refresh = AsyncMock()
    message = Message(
        author_type=AuthorType.USER,
        sender_identifier="+15550001111",
        recipient_identifier="+15550002222",
        channel=Channel.VOICE,
        text=TextObject(body="Tell me about today"),
        metadata=Metadata(testing=True),
    )

    # Exhaust the stream to trigger langfuse span
    async for _ in _impl.get_chat_response_stream(
        session=session, message=message, request_context=RequestContext()
    ):
        pass

    # Verify langfuse_message_span was called
    assert len(captured_kwargs) == 1
    kwargs = captured_kwargs[0]
    assert kwargs["user_id"] == user.id
    assert kwargs["agent_id"] == project.agent_id
    assert kwargs["channel"] == "voice"

    # Verify input was set
    assert any(
        c.get("input") == {"content": "Tell me about today"} for c in trace_io_calls
    )

    # Verify output was set (stream collected "streamed")
    assert any("output" in c for c in trace_io_calls)
    output_call = next(c for c in trace_io_calls if "output" in c)
    assert output_call["output"]["content"] == "streamed"
