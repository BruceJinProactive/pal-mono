"""Tests covering agent dispatch paths in message_service.

These tests verify behavior that must remain identical before and after
the _dispatch_agent_async extraction and langfuse_message_span wiring.
"""

import sys
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib import import_module
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from api.schemas.chat.message import AuthorType, Message, Metadata, TextObject
from db.tables.types import Channel
from utils.request_context import RequestContext

# ---------------------------------------------------------------------------
# Shared test infrastructure (mirrors existing test patterns)
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

            async def run(self, _input, stream=False):
                return SimpleNamespace(
                    content="noop", escalated=False, closing_conversation=False
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
                content="legacy response", escalated=False, closing_conversation=False
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
    transaction_service_mod.get_order_by_order_id_store_vendor = _not_implemented  # type: ignore[attr-defined]
    transaction_service_mod.save_order = _not_implemented  # type: ignore[attr-defined]
    reservation_service_mod.save_reservation_from_agent_async = _not_implemented  # type: ignore[attr-defined]
    reservation_service_mod.save_reservation = _not_implemented  # type: ignore[attr-defined]
    reservation_service_mod.save_waitlist = _not_implemented  # type: ignore[attr-defined]


class _FakeMessageRepo:
    def __init__(self):
        self.saved_messages: list[dict] = []
        self.created_message_kwargs: dict | None = None

    async def create_message(self, **kwargs):
        self.created_message_kwargs = kwargs
        return SimpleNamespace(conversation_id=uuid.uuid4())

    async def add_message_to_conversation(self, conversation_id, message_body):
        self.saved_messages.append(
            {"conversation_id": conversation_id, "body": message_body}
        )


class _FakeConversationRepo:
    def __init__(self):
        self.updated_conversations: list = []

    async def get_conversation_by_id(self, conversation_id):
        conv = SimpleNamespace(
            id=conversation_id,
            status="active",
            agent_fingerprint=None,
            prompt_fingerprint=None,
            transfer_purpose=None,
            vapi_control_url=None,
        )
        self.updated_conversations.append(conv)
        return conv


class _FakeAgentRepo:
    async def get_agent(self, agent_id):
        return SimpleNamespace(language=None)


def _make_project(*, use_pal_agents: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        name="test-project",
        account_id=uuid.uuid4(),
        raw_config={"use_pal_agents": use_pal_agents},
        agent_id=uuid.uuid4(),
        timezone="America/Los_Angeles",
        account=SimpleNamespace(name="test-account"),
        agent=SimpleNamespace(filler_words=None),
    )


def _make_message(text: str = "Hello") -> Message:
    return Message(
        author_type=AuthorType.USER,
        sender_identifier="+15550001111",
        recipient_identifier="+15550002222",
        channel=Channel.SMS,
        text=TextObject(body=text),
        metadata=Metadata(testing=True),
    )


def _setup_common_mocks(monkeypatch, *, project, user, message_repo):
    """Wire common monkeypatches for _implementation."""
    from services.message_service import _implementation

    conversation_repo = _FakeConversationRepo()

    async def _fake_get_project_async(session, message):
        return project

    async def _fake_get_user_async(session, proj, message):
        return user, False

    monkeypatch.setattr(
        _implementation.db, "MessageRepositoryAsync", lambda session: message_repo
    )
    monkeypatch.setattr(
        _implementation.db,
        "ConversationRepositoryAsync",
        lambda session: conversation_repo,
    )
    monkeypatch.setattr(
        _implementation.db, "AgentRepositoryAsync", lambda session: _FakeAgentRepo()
    )
    monkeypatch.setattr(
        _implementation.project_service, "get_project_async", _fake_get_project_async
    )
    monkeypatch.setattr(
        _implementation.user_service, "get_user_async", _fake_get_user_async
    )
    monkeypatch.setattr(_implementation, "record_duration", lambda *a, **kw: None)

    return _implementation, conversation_repo


# ---------------------------------------------------------------------------
# Test: pal-agents path formats conversation history correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pal_agents_path_formats_history_with_prior_messages(monkeypatch):
    """Verify conversation history is formatted as XML block and current message excluded."""
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_agent_shims_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)

    project = _make_project(use_pal_agents=True)
    user = SimpleNamespace(id=uuid.uuid4())
    message_repo = _FakeMessageRepo()

    _impl, _ = _setup_common_mocks(
        monkeypatch, project=project, user=user, message_repo=message_repo
    )

    captured_inputs: list = []

    async def _fake_construct_agent_spec(**kwargs):
        return SimpleNamespace()

    class _CapturePalAgent:
        def __init__(self, spec=None):
            self.spec = spec

        async def run(self, pal_input, stream=False):
            captured_inputs.append(pal_input.content)
            return SimpleNamespace(
                content="response", escalated=False, closing_conversation=False
            )

    # Return history with 3 messages: 2 prior + current (last)
    async def _fake_query_history_messages(*args, **kwargs):
        return [
            SimpleNamespace(role="user", content="Hi"),
            SimpleNamespace(role="assistant", content="Hello! How can I help?"),
            SimpleNamespace(role="user", content="What is the menu?"),
        ]

    monkeypatch.setattr(
        _impl.agent_service, "construct_agent_spec", _fake_construct_agent_spec
    )
    monkeypatch.setattr(_impl, "PalAgent", _CapturePalAgent)
    monkeypatch.setattr(_impl, "query_history_messages", _fake_query_history_messages)

    session = AsyncMock()
    session.refresh = AsyncMock()
    message = _make_message("What is the menu?")

    await _impl.get_chat_response_async(
        session=session, message=message, request_context=RequestContext()
    )

    assert len(captured_inputs) == 1
    content = captured_inputs[0]
    # Should have conversation_history XML block
    assert "<conversation_history>" in content
    assert "User: Hi" in content
    assert "Assistant: Hello! How can I help?" in content
    # Current message should NOT be inside history block
    assert content.endswith("User: What is the menu?")
    # Current message should be outside the XML block
    assert "</conversation_history>" in content
    parts = content.split("</conversation_history>")
    assert "User: What is the menu?" in parts[1]


@pytest.mark.asyncio
async def test_pal_agents_email_extraction_timeout_keeps_current_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify email S3 extraction timeout falls back to the original body."""
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_agent_shims_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)

    project = _make_project(use_pal_agents=True)
    user = SimpleNamespace(id=uuid.uuid4())
    message_repo = _FakeMessageRepo()

    _impl, _ = _setup_common_mocks(
        monkeypatch, project=project, user=user, message_repo=message_repo
    )

    captured_inputs: list[str] = []

    async def _fake_construct_agent_spec(**kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace()

    class _CapturePalAgent:
        def __init__(self, spec: Any = None) -> None:
            self.spec = spec

        async def run(
            self,
            pal_input: Any,
            stream: bool = False,
        ) -> SimpleNamespace:
            captured_inputs.append(pal_input.content)
            return SimpleNamespace(
                content="response", escalated=False, closing_conversation=False
            )

    async def _fake_query_history_messages(*args: Any, **kwargs: Any) -> list:
        return []

    async def _slow_extract_email_body(
        message_id: str,
        fallback_body: str = "",
    ) -> str:
        await _impl.asyncio.sleep(1)
        return f"{message_id}:{fallback_body}"

    monkeypatch.setattr(
        _impl.agent_service, "construct_agent_spec", _fake_construct_agent_spec
    )
    monkeypatch.setattr(_impl, "PalAgent", _CapturePalAgent)
    monkeypatch.setattr(_impl, "query_history_messages", _fake_query_history_messages)
    monkeypatch.setattr(_impl, "EMAIL_BODY_EXTRACTION_TIMEOUT_SECONDS", 0.001)
    monkeypatch.setattr(_impl, "_extract_email_body_from_s3", _slow_extract_email_body)

    session = AsyncMock()
    session.refresh = AsyncMock()
    message = _make_message("Original email body")
    message.channel = Channel.EMAIL
    message.channel_info = {"messageId": "ses-message-id"}

    await _impl.get_chat_response_async(
        session=session, message=message, request_context=RequestContext()
    )

    assert captured_inputs == ["User: Original email body"]


# ---------------------------------------------------------------------------
# Test: pal-agents path with context_modifier callback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pal_agents_path_applies_context_modifier(monkeypatch):
    """Verify context_modifier callback is invoked on RuntimeContext."""
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_agent_shims_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)

    project = _make_project(use_pal_agents=True)
    user = SimpleNamespace(id=uuid.uuid4())
    message_repo = _FakeMessageRepo()

    _impl, _ = _setup_common_mocks(
        monkeypatch, project=project, user=user, message_repo=message_repo
    )

    captured_runtime_contexts: list = []

    async def _fake_construct_agent_spec(**kwargs):
        return SimpleNamespace()

    class _CapturePalAgent:
        def __init__(self, spec=None):
            self.spec = spec

        async def run(self, pal_input, stream=False):
            captured_runtime_contexts.append(pal_input.runtime_context)
            return SimpleNamespace(
                content="response", escalated=False, closing_conversation=False
            )

    async def _fake_query_history_messages(*args, **kwargs):
        return []

    monkeypatch.setattr(
        _impl.agent_service, "construct_agent_spec", _fake_construct_agent_spec
    )
    monkeypatch.setattr(_impl, "PalAgent", _CapturePalAgent)
    monkeypatch.setattr(_impl, "query_history_messages", _fake_query_history_messages)

    session = AsyncMock()
    session.refresh = AsyncMock()
    message = _make_message("Hello")

    # Define a context_modifier that adds a custom field
    def my_modifier(ctx):
        ctx.custom_field = "injected_value"

    await _impl.get_chat_response_async(
        session=session,
        message=message,
        request_context=RequestContext(),
        context_modifier=my_modifier,
    )

    assert len(captured_runtime_contexts) == 1
    assert captured_runtime_contexts[0].custom_field == "injected_value"


# ---------------------------------------------------------------------------
# Test: pal-agents path hydrates previous tool results from external cache
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pal_agents_path_attaches_external_previous_tool_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """External cache hits are attached to RuntimeContext before PalAgent.run."""
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_agent_shims_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)

    project = _make_project(use_pal_agents=True)
    user = SimpleNamespace(id=uuid.uuid4())
    message_repo = _FakeMessageRepo()

    _impl, _ = _setup_common_mocks(
        monkeypatch, project=project, user=user, message_repo=message_repo
    )

    previous_tool_results: list[dict[str, object]] = [
        {
            "tool_name": "toast_takeout_create_order_v1",
            "cacheable_result": {"status": "success", "order_state": "created"},
            "status": "success",
        }
    ]
    captured_previous_results: list[object | None] = []

    async def _fake_get_tool_results(
        conversation_id: str,
    ) -> list[dict[str, object]]:
        return previous_tool_results

    async def _fake_construct_agent_spec(**kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace()

    class _CapturePalAgent:
        def __init__(self, spec: object | None = None) -> None:
            self.spec = spec

        async def run(self, pal_input: Any, stream: bool = False) -> SimpleNamespace:
            captured_previous_results.append(
                getattr(pal_input.runtime_context, "previous_tool_results", None)
            )
            return SimpleNamespace(
                content="response", escalated=False, closing_conversation=False
            )

    async def _fake_query_history_messages(*args: Any, **kwargs: Any) -> list[object]:
        return []

    monkeypatch.setattr(_impl, "get_tool_results", _fake_get_tool_results)
    monkeypatch.setattr(
        _impl.agent_service, "construct_agent_spec", _fake_construct_agent_spec
    )
    monkeypatch.setattr(_impl, "PalAgent", _CapturePalAgent)
    monkeypatch.setattr(_impl, "query_history_messages", _fake_query_history_messages)

    session = AsyncMock()
    session.refresh = AsyncMock()

    await _impl.get_chat_response_async(
        session=session,
        message=_make_message("What happened with my order?"),
        request_context=RequestContext(),
    )

    assert captured_previous_results == [previous_tool_results]


@pytest.mark.asyncio
async def test_pal_agents_path_uses_process_local_fallback_on_cache_miss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """External cache misses leave RuntimeContext untouched for pal-agents fallback."""
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_agent_shims_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)

    project = _make_project(use_pal_agents=True)
    user = SimpleNamespace(id=uuid.uuid4())
    message_repo = _FakeMessageRepo()

    _impl, _ = _setup_common_mocks(
        monkeypatch, project=project, user=user, message_repo=message_repo
    )

    captured_previous_results: list[object | None] = []

    async def _fake_get_tool_results(
        conversation_id: str,
    ) -> list[dict[str, object]]:
        return []

    async def _fake_construct_agent_spec(**kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace()

    class _CapturePalAgent:
        def __init__(self, spec: object | None = None) -> None:
            self.spec = spec

        async def run(self, pal_input: Any, stream: bool = False) -> SimpleNamespace:
            captured_previous_results.append(
                getattr(pal_input.runtime_context, "previous_tool_results", None)
            )
            return SimpleNamespace(
                content="response", escalated=False, closing_conversation=False
            )

    async def _fake_query_history_messages(*args: Any, **kwargs: Any) -> list[object]:
        return []

    monkeypatch.setattr(_impl, "get_tool_results", _fake_get_tool_results)
    monkeypatch.setattr(
        _impl.agent_service, "construct_agent_spec", _fake_construct_agent_spec
    )
    monkeypatch.setattr(_impl, "PalAgent", _CapturePalAgent)
    monkeypatch.setattr(_impl, "query_history_messages", _fake_query_history_messages)

    session = AsyncMock()
    session.refresh = AsyncMock()

    await _impl.get_chat_response_async(
        session=session,
        message=_make_message("What happened with my order?"),
        request_context=RequestContext(),
    )

    assert captured_previous_results == [None]


@pytest.mark.asyncio
async def test_previous_tool_result_read_failure_is_best_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cache read failures do not prevent RuntimeContext construction."""
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_agent_shims_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)

    from services.message_service import _implementation as _impl

    async def _raise_get_tool_results(
        conversation_id: str,
    ) -> list[dict[str, object]]:
        raise RuntimeError("cache unavailable")

    monkeypatch.setattr(_impl, "get_tool_results", _raise_get_tool_results)

    runtime_context = _impl.RuntimeContext(timezone="UTC", channel="sms")

    await _impl._hydrate_previous_tool_results(runtime_context, uuid.uuid4())

    assert getattr(runtime_context, "previous_tool_results", None) is None


@pytest.mark.asyncio
async def test_pal_agents_path_continues_when_previous_tool_result_read_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Redis read failures do not break non-streaming chat responses."""
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_agent_shims_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)

    project = _make_project(use_pal_agents=True)
    user = SimpleNamespace(id=uuid.uuid4())
    message_repo = _FakeMessageRepo()

    _impl, _ = _setup_common_mocks(
        monkeypatch, project=project, user=user, message_repo=message_repo
    )

    captured_previous_results: list[object | None] = []

    async def _raise_get_tool_results(
        conversation_id: str,
    ) -> list[dict[str, object]]:
        raise TimeoutError("redis timed out")

    async def _fake_construct_agent_spec(**kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace()

    class _CapturePalAgent:
        def __init__(self, spec: object | None = None) -> None:
            self.spec = spec

        async def run(self, pal_input: Any, stream: bool = False) -> SimpleNamespace:
            captured_previous_results.append(
                getattr(pal_input.runtime_context, "previous_tool_results", None)
            )
            return SimpleNamespace(
                content="response", escalated=False, closing_conversation=False
            )

    async def _fake_query_history_messages(*args: Any, **kwargs: Any) -> list[object]:
        return []

    monkeypatch.setattr(_impl, "get_tool_results", _raise_get_tool_results)
    monkeypatch.setattr(
        _impl.agent_service, "construct_agent_spec", _fake_construct_agent_spec
    )
    monkeypatch.setattr(_impl, "PalAgent", _CapturePalAgent)
    monkeypatch.setattr(_impl, "query_history_messages", _fake_query_history_messages)

    session = AsyncMock()
    session.refresh = AsyncMock()

    result = await _impl.get_chat_response_async(
        session=session,
        message=_make_message("Can you check my order?"),
        request_context=RequestContext(),
    )

    assert captured_previous_results == [None]
    assert any(
        response_message.text and response_message.text.body == "response"
        for response_message in result
    )


@pytest.mark.asyncio
async def test_streaming_pal_agents_path_attaches_external_previous_tool_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Streaming pal-agents runs receive external previous tool results too."""
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_agent_shims_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)

    project = _make_project(use_pal_agents=True)
    user = SimpleNamespace(id=uuid.uuid4())
    message_repo = _FakeMessageRepo()

    _impl, _ = _setup_common_mocks(
        monkeypatch, project=project, user=user, message_repo=message_repo
    )

    previous_tool_results: list[dict[str, object]] = [
        {
            "tool_name": "adora_process_order",
            "cacheable_result": {"status": "success", "order_status": "pending"},
            "status": "success",
        }
    ]
    captured_previous_results: list[object | None] = []

    @asynccontextmanager
    async def _fake_trace_async_block(
        name: str,
        resource: str | None = None,
        service: str | None = None,
        tags: dict[str, str] | None = None,
    ) -> AsyncIterator[None]:
        yield None

    async def _fake_get_tool_results(
        conversation_id: str,
    ) -> list[dict[str, object]]:
        return previous_tool_results

    async def _fake_construct_agent_spec(**kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace()

    class _CapturePalAgent:
        def __init__(self, spec: object | None = None) -> None:
            self.spec = spec

        async def run(self, pal_input: Any, stream: bool = False) -> AsyncIterator[Any]:
            captured_previous_results.append(
                getattr(pal_input.runtime_context, "previous_tool_results", None)
            )

            async def _stream() -> AsyncIterator[SimpleNamespace]:
                yield SimpleNamespace(content="Got it")

            return _stream()

    async def _fake_query_history_messages(*args: Any, **kwargs: Any) -> list[object]:
        return []

    monkeypatch.setattr(_impl, "trace_async_block", _fake_trace_async_block)
    monkeypatch.setattr(_impl, "get_tool_results", _fake_get_tool_results)
    monkeypatch.setattr(
        _impl.agent_service, "construct_agent_spec", _fake_construct_agent_spec
    )
    monkeypatch.setattr(_impl, "PalAgent", _CapturePalAgent)
    monkeypatch.setattr(_impl, "query_history_messages", _fake_query_history_messages)

    session = AsyncMock()
    session.refresh = AsyncMock()

    chunks = [
        chunk
        async for chunk in _impl.get_chat_response_stream(
            session=session,
            message=_make_message("Any update?"),
            request_context=RequestContext(),
        )
    ]

    assert chunks
    assert captured_previous_results == [previous_tool_results]


@pytest.mark.asyncio
async def test_streaming_pal_agents_path_continues_when_previous_tool_result_read_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Redis read failures do not break streaming chat responses."""
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_agent_shims_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)

    project = _make_project(use_pal_agents=True)
    user = SimpleNamespace(id=uuid.uuid4())
    message_repo = _FakeMessageRepo()

    _impl, _ = _setup_common_mocks(
        monkeypatch, project=project, user=user, message_repo=message_repo
    )

    captured_previous_results: list[object | None] = []

    @asynccontextmanager
    async def _fake_trace_async_block(
        name: str,
        resource: str | None = None,
        service: str | None = None,
        tags: dict[str, str] | None = None,
    ) -> AsyncIterator[None]:
        yield None

    async def _raise_get_tool_results(
        conversation_id: str,
    ) -> list[dict[str, object]]:
        raise TimeoutError("redis timed out")

    async def _fake_construct_agent_spec(**kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace()

    class _CapturePalAgent:
        def __init__(self, spec: object | None = None) -> None:
            self.spec = spec

        async def run(self, pal_input: Any, stream: bool = False) -> AsyncIterator[Any]:
            captured_previous_results.append(
                getattr(pal_input.runtime_context, "previous_tool_results", None)
            )

            async def _stream() -> AsyncIterator[SimpleNamespace]:
                yield SimpleNamespace(content="Still working")

            return _stream()

    async def _fake_query_history_messages(*args: Any, **kwargs: Any) -> list[object]:
        return []

    monkeypatch.setattr(_impl, "trace_async_block", _fake_trace_async_block)
    monkeypatch.setattr(_impl, "get_tool_results", _raise_get_tool_results)
    monkeypatch.setattr(
        _impl.agent_service, "construct_agent_spec", _fake_construct_agent_spec
    )
    monkeypatch.setattr(_impl, "PalAgent", _CapturePalAgent)
    monkeypatch.setattr(_impl, "query_history_messages", _fake_query_history_messages)

    session = AsyncMock()
    session.refresh = AsyncMock()

    chunks = [
        chunk
        async for chunk in _impl.get_chat_response_stream(
            session=session,
            message=_make_message("Any update?"),
            request_context=RequestContext(),
        )
    ]

    contents = [
        chunk.choices[0].delta.content
        for chunk in chunks
        if chunk.choices[0].delta.content
    ]
    assert captured_previous_results == [None]
    assert "Still working" in contents


# ---------------------------------------------------------------------------
# Test: non-streaming closing_conversation updates conversation status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_nonstreaming_closing_conversation_updates_status(monkeypatch):
    """Verify closing_conversation=True triggers conversation status update."""
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_agent_shims_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)

    project = _make_project(use_pal_agents=True)
    user = SimpleNamespace(id=uuid.uuid4())
    message_repo = _FakeMessageRepo()

    _impl, conversation_repo = _setup_common_mocks(
        monkeypatch, project=project, user=user, message_repo=message_repo
    )

    async def _fake_construct_agent_spec(**kwargs):
        return SimpleNamespace()

    class _ClosingPalAgent:
        def __init__(self, spec=None):
            self.spec = spec

        async def run(self, pal_input, stream=False):
            return SimpleNamespace(
                content="Goodbye!", escalated=False, closing_conversation=True
            )

    async def _fake_query_history_messages(*args, **kwargs):
        return []

    monkeypatch.setattr(
        _impl.agent_service, "construct_agent_spec", _fake_construct_agent_spec
    )
    monkeypatch.setattr(_impl, "PalAgent", _ClosingPalAgent)
    monkeypatch.setattr(_impl, "query_history_messages", _fake_query_history_messages)

    session = AsyncMock()
    session.refresh = AsyncMock()
    session.flush = AsyncMock()
    message = _make_message("bye")

    result = await _impl.get_chat_response_async(
        session=session, message=message, request_context=RequestContext()
    )

    # Verify response was generated
    assert any(m.text and m.text.body == "Goodbye!" for m in result)

    # Verify conversation status was updated to CLOSING
    assert len(conversation_repo.updated_conversations) >= 1
    conv = conversation_repo.updated_conversations[-1]
    assert conv.status == _impl.db.ConversationStatus.CLOSING


# ---------------------------------------------------------------------------
# Test: non-streaming BREAK token splits messages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_nonstreaming_break_token_splits_messages(monkeypatch):
    """Verify <BREAK> token in output creates multiple response messages."""
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_agent_shims_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)

    project = _make_project(use_pal_agents=True)
    user = SimpleNamespace(id=uuid.uuid4())
    message_repo = _FakeMessageRepo()

    _impl, _ = _setup_common_mocks(
        monkeypatch, project=project, user=user, message_repo=message_repo
    )

    async def _fake_construct_agent_spec(**kwargs):
        return SimpleNamespace()

    class _BreakPalAgent:
        def __init__(self, spec=None):
            self.spec = spec

        async def run(self, pal_input, stream=False):
            return SimpleNamespace(
                content="Part one<BREAK>Part two<BREAK>Part three",
                escalated=False,
                closing_conversation=False,
            )

    async def _fake_query_history_messages(*args, **kwargs):
        return []

    monkeypatch.setattr(
        _impl.agent_service, "construct_agent_spec", _fake_construct_agent_spec
    )
    monkeypatch.setattr(_impl, "PalAgent", _BreakPalAgent)
    monkeypatch.setattr(_impl, "query_history_messages", _fake_query_history_messages)

    session = AsyncMock()
    session.refresh = AsyncMock()
    message = _make_message("Tell me about specials")

    result = await _impl.get_chat_response_async(
        session=session, message=message, request_context=RequestContext()
    )

    # Should have 3 response messages from the BREAK split
    texts = [m.text.body for m in result if m.text]
    assert texts == ["Part one", "Part two", "Part three"]


# ---------------------------------------------------------------------------
# Test: pal-agents non-streaming reservation persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_nonstreaming_reservation_persistence(monkeypatch):
    """Verify reservation_details from pal-agents output are persisted."""
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_agent_shims_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)

    project = _make_project(use_pal_agents=True)
    user = SimpleNamespace(id=uuid.uuid4())
    message_repo = _FakeMessageRepo()

    _impl, _ = _setup_common_mocks(
        monkeypatch, project=project, user=user, message_repo=message_repo
    )

    saved_reservations: list = []

    async def _fake_construct_agent_spec(**kwargs):
        return SimpleNamespace()

    class _ReservationPalAgent:
        def __init__(self, spec=None):
            self.spec = spec

        async def run(self, pal_input, stream=False):
            return SimpleNamespace(
                content="Reservation confirmed!",
                escalated=False,
                closing_conversation=False,
                reservation_details=SimpleNamespace(
                    vendor="resy",
                    entry_type="reservation",
                    reservation_id="RES-001",
                    store_id="STORE-1",
                    status="confirmed",
                    party_size=4,
                ),
            )

    async def _fake_query_history_messages(*args, **kwargs):
        return []

    async def _fake_save_reservation(session, reservation_details, conversation_id):
        saved_reservations.append(
            {
                "conversation_id": conversation_id,
                "vendor": reservation_details.vendor,
                "reservation_id": reservation_details.reservation_id,
                "party_size": reservation_details.party_size,
            }
        )

    monkeypatch.setattr(
        _impl.agent_service, "construct_agent_spec", _fake_construct_agent_spec
    )
    monkeypatch.setattr(_impl, "PalAgent", _ReservationPalAgent)
    monkeypatch.setattr(_impl, "query_history_messages", _fake_query_history_messages)
    monkeypatch.setattr(
        _impl.reservation_service,
        "save_reservation_from_agent_async",
        _fake_save_reservation,
    )

    session = AsyncMock()
    session.refresh = AsyncMock()
    message = _make_message("Book a table for 4")

    result = await _impl.get_chat_response_async(
        session=session, message=message, request_context=RequestContext()
    )

    assert any(m.text and "Reservation confirmed" in m.text.body for m in result)
    assert len(saved_reservations) == 1
    assert saved_reservations[0]["vendor"] == "resy"
    assert saved_reservations[0]["party_size"] == 4


# ---------------------------------------------------------------------------
# Test: streaming path with transfer_purpose mid-stream persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_streaming_transfer_purpose_persisted(monkeypatch):
    """Verify transfer_purpose from streaming chunk is persisted to conversation."""
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_agent_shims_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)

    project = _make_project(use_pal_agents=True)
    user = SimpleNamespace(id=uuid.uuid4())
    message_repo = _FakeMessageRepo()

    _impl, conversation_repo = _setup_common_mocks(
        monkeypatch, project=project, user=user, message_repo=message_repo
    )

    @asynccontextmanager
    async def _fake_trace_async_block(name, resource=None, service=None, tags=None):
        yield None

    async def _fake_construct_agent_spec(**kwargs):
        return SimpleNamespace()

    class _TransferPalAgent:
        def __init__(self, spec=None):
            self.spec = spec

        async def run(self, pal_input, stream=False):
            async def _stream():
                yield SimpleNamespace(content="Let me transfer you")
                # Chunk with transfer_purpose
                yield SimpleNamespace(content="", transfer_purpose="billing_inquiry")
                yield SimpleNamespace(content=" to billing.")

            return _stream()

    async def _fake_query_history_messages(*args, **kwargs):
        return []

    monkeypatch.setattr(_impl, "trace_async_block", _fake_trace_async_block)
    monkeypatch.setattr(
        _impl.agent_service, "construct_agent_spec", _fake_construct_agent_spec
    )
    monkeypatch.setattr(_impl, "PalAgent", _TransferPalAgent)
    monkeypatch.setattr(_impl, "query_history_messages", _fake_query_history_messages)

    session = AsyncMock()
    session.refresh = AsyncMock()
    session.commit = AsyncMock()
    message = _make_message("I need help with my bill")

    chunks = [
        chunk
        async for chunk in _impl.get_chat_response_stream(
            session=session, message=message, request_context=RequestContext()
        )
    ]

    # Verify content chunks came through
    contents = [
        c.choices[0].delta.content for c in chunks if c.choices[0].delta.content
    ]
    assert "Let me transfer you" in contents

    # Verify transfer_purpose was persisted to conversation
    assert len(conversation_repo.updated_conversations) >= 1
    persisted_conv = next(
        (c for c in conversation_repo.updated_conversations if c.transfer_purpose),
        None,
    )
    assert persisted_conv is not None
    assert persisted_conv.transfer_purpose == "billing_inquiry"


# ---------------------------------------------------------------------------
# Test: streaming pal-agents path formats history correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_streaming_pal_agents_formats_history(monkeypatch):
    """Verify streaming path formats conversation history same as non-streaming."""
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_agent_shims_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)

    project = _make_project(use_pal_agents=True)
    user = SimpleNamespace(id=uuid.uuid4())
    message_repo = _FakeMessageRepo()

    _impl, _ = _setup_common_mocks(
        monkeypatch, project=project, user=user, message_repo=message_repo
    )

    @asynccontextmanager
    async def _fake_trace_async_block(name, resource=None, service=None, tags=None):
        yield None

    captured_inputs: list = []

    async def _fake_construct_agent_spec(**kwargs):
        return SimpleNamespace()

    class _CapturePalAgent:
        def __init__(self, spec=None):
            self.spec = spec

        async def run(self, pal_input, stream=False):
            captured_inputs.append(pal_input.content)

            async def _stream():
                yield SimpleNamespace(content="Got it")

            return _stream()

    async def _fake_query_history_messages(*args, **kwargs):
        return [
            SimpleNamespace(role="user", content="Previous question"),
            SimpleNamespace(role="assistant", content="Previous answer"),
            SimpleNamespace(role="user", content="Follow up"),
        ]

    monkeypatch.setattr(_impl, "trace_async_block", _fake_trace_async_block)
    monkeypatch.setattr(
        _impl.agent_service, "construct_agent_spec", _fake_construct_agent_spec
    )
    monkeypatch.setattr(_impl, "PalAgent", _CapturePalAgent)
    monkeypatch.setattr(_impl, "query_history_messages", _fake_query_history_messages)

    session = AsyncMock()
    session.refresh = AsyncMock()
    message = _make_message("Follow up")

    # Exhaust the stream to trigger agent execution
    async for _ in _impl.get_chat_response_stream(
        session=session, message=message, request_context=RequestContext()
    ):
        pass

    assert len(captured_inputs) == 1
    content = captured_inputs[0]
    assert "<conversation_history>" in content
    assert "User: Previous question" in content
    assert "Assistant: Previous answer" in content
    # Current message excluded from history, appended after
    assert content.endswith("User: Follow up")


# ---------------------------------------------------------------------------
# Test: streaming saves final message to database after stream completes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_streaming_saves_collected_content_to_db(monkeypatch):
    """Verify that after streaming, the full response is saved to database."""
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_agent_shims_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)

    project = _make_project(use_pal_agents=True)
    user = SimpleNamespace(id=uuid.uuid4())
    message_repo = _FakeMessageRepo()

    _impl, _ = _setup_common_mocks(
        monkeypatch, project=project, user=user, message_repo=message_repo
    )

    @asynccontextmanager
    async def _fake_trace_async_block(name, resource=None, service=None, tags=None):
        yield None

    async def _fake_construct_agent_spec(**kwargs):
        return SimpleNamespace()

    class _MultiChunkPalAgent:
        def __init__(self, spec=None):
            self.spec = spec

        async def run(self, pal_input, stream=False):
            async def _stream():
                yield SimpleNamespace(content="Hello ")
                yield SimpleNamespace(content="world ")
                yield SimpleNamespace(content="!")

            return _stream()

    async def _fake_query_history_messages(*args, **kwargs):
        return []

    monkeypatch.setattr(_impl, "trace_async_block", _fake_trace_async_block)
    monkeypatch.setattr(
        _impl.agent_service, "construct_agent_spec", _fake_construct_agent_spec
    )
    monkeypatch.setattr(_impl, "PalAgent", _MultiChunkPalAgent)
    monkeypatch.setattr(_impl, "query_history_messages", _fake_query_history_messages)

    session = AsyncMock()
    session.refresh = AsyncMock()
    message = _make_message("Hi")

    chunks = [
        chunk
        async for chunk in _impl.get_chat_response_stream(
            session=session, message=message, request_context=RequestContext()
        )
    ]

    # Verify chunks yielded
    assert len(chunks) == 3

    # Verify full response saved to DB
    assert len(message_repo.saved_messages) == 1
    saved_body = message_repo.saved_messages[0]["body"]
    assert saved_body["text"]["body"] == "Hello world !"


# ---------------------------------------------------------------------------
# Test: non-streaming legacy path still works end-to-end
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_legacy_path_end_to_end(monkeypatch):
    """Verify legacy (non-pal-agents) path produces correct response."""
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_agent_shims_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)

    project = _make_project(use_pal_agents=False)
    user = SimpleNamespace(id=uuid.uuid4())
    message_repo = _FakeMessageRepo()

    _impl, _ = _setup_common_mocks(
        monkeypatch, project=project, user=user, message_repo=message_repo
    )

    async def _fake_construct_agent_config(**kwargs):
        return SimpleNamespace(stream=False)

    class _TestAgent:
        def __init__(self, config):
            self.config = config

        async def arun(self, _input):
            return SimpleNamespace(
                content="Legacy agent reply",
                escalated=False,
                closing_conversation=False,
            )

    async def _fake_get_agent_input(**kwargs):
        return SimpleNamespace(content="input")

    async def _fake_query_history_messages(*args, **kwargs):
        return []

    monkeypatch.setattr(
        _impl.agent_service,
        "construct_agent_config",
        _fake_construct_agent_config,
    )
    monkeypatch.setattr(_impl, "Agent", _TestAgent)
    monkeypatch.setattr(
        _impl._utils, "get_agent_input_from_message", _fake_get_agent_input
    )
    monkeypatch.setattr(_impl, "query_history_messages", _fake_query_history_messages)

    session = AsyncMock()
    session.refresh = AsyncMock()
    message = _make_message("Hello")

    result = await _impl.get_chat_response_async(
        session=session, message=message, request_context=RequestContext()
    )

    assert len(result) >= 1
    assert result[0].text.body == "Legacy agent reply"
    assert result[0].author_type == AuthorType.AGENT
    assert result[0].metadata.account_name == "test-account"
    assert result[0].metadata.project_name == "test-project"


# ---------------------------------------------------------------------------
# Test: store_status (computed from project hours) lands on the RuntimeContext
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_store_status_wired_into_runtime_context(monkeypatch):
    """compute_store_status output is attached to the RuntimeContext (non-streaming)."""
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_agent_shims_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)

    project = _make_project(use_pal_agents=True)
    # True 24/7: each day's close is the NEXT day's 00:00, so the schedule covers
    # every instant with no end-of-day gap. (A close of "2359" would leave the store
    # "closed" for the 23:59:00-23:59:59 minute.) The production path uses real
    # wall-clock now, so this keeps the assertion deterministic.
    project.business_hours = {
        "regular_hours": {
            "periods": [
                {
                    "open": {"day": d, "time": "0000"},
                    "close": {"day": (d + 1) % 7, "time": "0000"},
                }
                for d in range(7)
            ]
        }
    }
    project.store_hours = None
    user = SimpleNamespace(id=uuid.uuid4())
    message_repo = _FakeMessageRepo()

    _impl, _ = _setup_common_mocks(
        monkeypatch, project=project, user=user, message_repo=message_repo
    )

    captured_runtime_contexts: list = []

    async def _fake_construct_agent_spec(**kwargs):
        return SimpleNamespace()

    class _CapturePalAgent:
        def __init__(self, spec=None):
            self.spec = spec

        async def run(self, pal_input, stream=False):
            captured_runtime_contexts.append(pal_input.runtime_context)
            return SimpleNamespace(
                content="response", escalated=False, closing_conversation=False
            )

    async def _fake_query_history_messages(*args, **kwargs):
        return []

    monkeypatch.setattr(
        _impl.agent_service, "construct_agent_spec", _fake_construct_agent_spec
    )
    monkeypatch.setattr(_impl, "PalAgent", _CapturePalAgent)
    monkeypatch.setattr(_impl, "query_history_messages", _fake_query_history_messages)

    session = AsyncMock()
    session.refresh = AsyncMock()

    await _impl.get_chat_response_async(
        session=session,
        message=_make_message("Hello"),
        request_context=RequestContext(),
    )

    assert len(captured_runtime_contexts) == 1
    store_status = captured_runtime_contexts[0].store_status
    assert store_status["status"] == "open"
    assert store_status["is_open"] is True
    assert store_status["source"] == "business_hours"
