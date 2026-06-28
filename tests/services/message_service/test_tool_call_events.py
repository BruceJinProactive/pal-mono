"""Tests for generic tool call event collection and persistence."""

import asyncio
import sys
import uuid
from contextlib import asynccontextmanager
from importlib import import_module
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

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
            def __init__(self, spec=None):  # type: ignore[no-untyped-def]
                self.spec = spec

            async def run(
                self,
                _input: object,
                stream: bool = False,
                **_kwargs: Any,
            ) -> object:
                async def _stream():  # type: ignore[no-untyped-def]
                    if False:
                        yield None

                return _stream()

        class _NoopPalInput:
            def __init__(self, content="", runtime_context=None):  # type: ignore[no-untyped-def]
                self.content = content
                self.runtime_context = runtime_context

        class _NoopRuntimeContext:
            def __init__(self, **kwargs):  # type: ignore[no-untyped-def]
                self.__dict__.update(kwargs)

        pal_agents_pkg.Agent = _NoopPalAgent  # type: ignore[attr-defined]
        pal_agents_pkg.Input = _NoopPalInput  # type: ignore[attr-defined]
        input_mod.RuntimeContext = _NoopRuntimeContext  # type: ignore[attr-defined]

    knowledge_mod = ModuleType("pal_agents.providers.knowledge")
    monkeypatch.setitem(sys.modules, "pal_agents.providers.knowledge", knowledge_mod)

    class _NoopKnowledge:
        def __init__(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
            return

        async def as_text_async(self) -> str | None:
            return None

        def as_tool(self):  # type: ignore[no-untyped-def]
            return None

    knowledge_mod.Knowledge = _NoopKnowledge  # type: ignore[attr-defined]


def _install_services_shims_if_needed(monkeypatch: pytest.MonkeyPatch) -> None:
    real_services_pkg = import_module("services")
    _ensure_package_module(monkeypatch, "services", real_services_pkg)
    agent_service_mod = ModuleType("services.agent_service")
    project_service_mod = ModuleType("services.project_service")
    user_service_mod = ModuleType("services.user_service")
    transaction_service_mod = ModuleType("services.transaction_service")
    monkeypatch.setitem(sys.modules, "services.agent_service", agent_service_mod)
    monkeypatch.setitem(sys.modules, "services.project_service", project_service_mod)
    monkeypatch.setitem(sys.modules, "services.user_service", user_service_mod)
    monkeypatch.setitem(
        sys.modules, "services.transaction_service", transaction_service_mod
    )

    async def _not_implemented(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    agent_service_mod.construct_agent_config = _not_implemented  # type: ignore[attr-defined]
    agent_service_mod.construct_agent_spec = _not_implemented  # type: ignore[attr-defined]
    project_service_mod.get_project_async = _not_implemented  # type: ignore[attr-defined]
    user_service_mod.get_user_async = _not_implemented  # type: ignore[attr-defined]
    user_service_mod.create_user_async = _not_implemented  # type: ignore[attr-defined]
    transaction_service_mod.create_order_from_agent_async = _not_implemented  # type: ignore[attr-defined]
    transaction_service_mod.save_order = _not_implemented  # type: ignore[attr-defined]
    transaction_service_mod.get_order_by_order_id_store_vendor = _not_implemented  # type: ignore[attr-defined]


class _FakeMessageRepo:
    def __init__(self) -> None:
        self.request_conversation_id = uuid.uuid4()
        self.saved_conversation_id: uuid.UUID | None = None
        self.saved_message_body: dict | None = None
        self.created_messages: list[dict] = []

    async def create_message(self, **kwargs) -> SimpleNamespace:  # type: ignore[no-untyped-def]
        self.created_messages.append(kwargs)
        return SimpleNamespace(conversation_id=self.request_conversation_id)

    async def add_message_to_conversation(
        self, conversation_id: uuid.UUID, message_body: dict
    ) -> None:
        self.saved_conversation_id = conversation_id
        self.saved_message_body = message_body


class _FakeAgentRepo:
    async def get_agent(self, agent_id: uuid.UUID) -> SimpleNamespace:
        return SimpleNamespace(language=None)


async def _drain_background_tasks(module: Any) -> None:
    pending_tasks = list(module._background_tasks)
    if pending_tasks:
        await asyncio.gather(*pending_tasks, return_exceptions=True)
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_tool_result_cache_write_scheduler_skips_non_tool_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)
    from services.message_service import _implementation

    append_calls: list[tuple[str, dict[str, Any]]] = []

    async def _fake_append_tool_result(
        conversation_id: str, payload: dict[str, Any]
    ) -> None:
        append_calls.append((conversation_id, payload))

    monkeypatch.setattr(
        _implementation,
        "append_tool_result",
        _fake_append_tool_result,
    )
    _implementation._background_tasks.clear()

    conversation_id = uuid.uuid4()
    _implementation._schedule_tool_result_cache_writes(
        conversation_id,
        [
            {"type": "sms_followup", "payload": {"message": "send update"}},
            {"type": "tool_call", "payload": None},
            {"type": "tool_result_cache", "payload": None},
        ],
    )
    await _drain_background_tasks(_implementation)

    assert append_calls == []
    assert _implementation._background_tasks == set()


def test_tool_result_cache_write_scheduler_handles_schedule_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)
    from services.message_service import _implementation

    def _raise_append_tool_result(
        conversation_id: str,
        payload: dict[str, Any],
    ) -> None:
        raise RuntimeError("cache unavailable")

    monkeypatch.setattr(
        _implementation,
        "append_tool_result",
        _raise_append_tool_result,
    )
    _implementation._background_tasks.clear()

    _implementation._schedule_tool_result_cache_writes(
        uuid.uuid4(),
        [
            {
                "type": "tool_result_cache",
                "payload": {
                    "schema": "previous_tool_result.v1",
                    "tool_name": "check_hours",
                    "raw_result": '{"open":true}',
                },
            }
        ],
    )

    assert _implementation._background_tasks == set()


@pytest.mark.asyncio
async def test_tool_result_cache_write_done_callback_handles_cancelled_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)
    from services.message_service import _implementation

    async def _sleep_forever() -> None:
        await asyncio.sleep(3600)

    task = asyncio.create_task(_sleep_forever())
    _implementation._background_tasks.clear()
    _implementation._background_tasks.add(task)

    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    _implementation._handle_tool_result_cache_write_done(task)

    assert task not in _implementation._background_tasks


@pytest.mark.asyncio
async def test_tool_result_cache_write_done_callback_handles_failed_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)
    from services.message_service import _implementation

    async def _raise_error() -> None:
        raise RuntimeError("cache write failed")

    task = asyncio.create_task(_raise_error())
    _implementation._background_tasks.clear()
    _implementation._background_tasks.add(task)

    await asyncio.gather(task, return_exceptions=True)
    _implementation._handle_tool_result_cache_write_done(task)

    assert task not in _implementation._background_tasks


# ---------------------------------------------------------------------------
# Streaming path test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_streaming_tool_call_events_attached_to_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tool call events from streaming chunks are collected and saved in message body."""
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
        timezone="America/Los_Angeles",
        name="test-project",
    )

    @asynccontextmanager
    async def _fake_trace_async_block(
        name: str,
        resource: str | None = None,
        service: str | None = None,
        tags: dict | None = None,
    ):  # type: ignore[no-untyped-def]
        yield None

    async def _fake_get_project_async(session, message):  # type: ignore[no-untyped-def]
        return project

    async def _fake_get_user_async(session, project, message):  # type: ignore[no-untyped-def]
        return user, False

    async def _fake_construct_agent_spec(**kwargs):  # type: ignore[no-untyped-def]
        return SimpleNamespace()

    tool_events = [
        {
            "type": "tool_call",
            "payload": {
                "tool_name": "lookup_menu",
                "arguments": {"query": "pizza"},
                "result": '{"items": ["pepperoni", "margherita"]}',
            },
        },
        {
            "type": "tool_result_cache",
            "payload": {
                "schema": "previous_tool_result.v1",
                "tool_name": "lookup_menu",
                "raw_result": '{"items": ["pepperoni", "margherita"]}',
                "captured_at": "2026-06-22T20:00:00Z",
            },
        },
        {
            "type": "tool_call",
            "payload": {
                "tool_name": "place_order",
                "arguments": {"item": "pepperoni"},
                "result": '{"status": "success"}',
            },
        },
        {
            "type": "tool_result_cache",
            "payload": {
                "schema": "previous_tool_result.v1",
                "tool_name": "place_order",
                "raw_result": '{"status": "success"}',
                "captured_at": "2026-06-22T20:00:01Z",
            },
        },
    ]
    sms_followup_event = {
        "type": "sms_followup",
        "source": "adora_process_order",
        "payload": {"item_recap": "1 large pepperoni pizza."},
    }
    prefetch_event = {
        "type": "tool_result_cache",
        "payload": {
            "schema": "previous_tool_result.v1",
            "tool_name": "adora_wait_time_prefetch_v1",
            "raw_result": '{"takeout_minutes":20}',
            "captured_at": "2026-06-22T20:00:02Z",
        },
    }
    collected_sms_events: list[dict] = []
    captured_prefetch_sinks: list[Any] = []
    append_calls: list[tuple[str, dict[str, Any]]] = []

    async def _fake_append_tool_result(
        conversation_id: str, payload: dict[str, Any]
    ) -> None:
        append_calls.append((conversation_id, payload))

    class _EventStreamPalAgent:
        def __init__(self, spec=None):  # type: ignore[no-untyped-def]
            self.spec = spec

        async def run(
            self,
            pal_input: object,
            stream: bool = False,
            *,
            prefetch_result_sink: Any | None = None,
        ) -> object:
            captured_prefetch_sinks.append(prefetch_result_sink)

            async def _stream():  # type: ignore[no-untyped-def]
                # Content chunk
                yield SimpleNamespace(content="Here's your order!")
                # Event chunk (empty content, carries events)
                yield SimpleNamespace(
                    content="", events=[*tool_events, sms_followup_event]
                )

            return _stream()

    async def _fake_query_history_messages(*args, **kwargs):  # type: ignore[no-untyped-def]
        return []

    fake_session = AsyncMock()
    fake_session.commit = AsyncMock()
    fake_session.rollback = AsyncMock()

    monkeypatch.setattr(_implementation, "trace_async_block", _fake_trace_async_block)
    monkeypatch.setattr(
        _implementation.db, "MessageRepositoryAsync", lambda session: message_repo
    )
    monkeypatch.setattr(
        _implementation.db, "AgentRepositoryAsync", lambda session: agent_repo
    )
    monkeypatch.setattr(
        _implementation.project_service,
        "get_project_async",
        _fake_get_project_async,
    )
    monkeypatch.setattr(
        _implementation.user_service, "get_user_async", _fake_get_user_async
    )
    monkeypatch.setattr(
        _implementation.agent_service,
        "construct_agent_spec",
        _fake_construct_agent_spec,
    )
    monkeypatch.setattr(_implementation, "PalAgent", _EventStreamPalAgent)
    monkeypatch.setattr(
        _implementation, "query_history_messages", _fake_query_history_messages
    )
    monkeypatch.setattr(_implementation, "record_duration", lambda *a, **kw: None)
    monkeypatch.setattr(
        _implementation,
        "append_tool_result",
        _fake_append_tool_result,
    )
    _implementation._background_tasks.clear()

    message = Message(
        author_type=AuthorType.USER,
        sender_identifier="+15550001111",
        recipient_identifier="+15550002222",
        channel=Channel.VOICE,
        text=TextObject(body="I want pizza"),
        metadata=Metadata(testing=True),
    )

    # Consume the stream
    chunks = [
        chunk
        async for chunk in _implementation.get_chat_response_stream(
            session=fake_session,
            message=message,
            request_context=RequestContext(),
            event_collector=collected_sms_events.append,
        )
    ]
    assert len(captured_prefetch_sinks) == 1
    assert callable(captured_prefetch_sinks[0])
    captured_prefetch_sinks[0](prefetch_event)
    await _drain_background_tasks(_implementation)

    # Verify content chunks were yielded
    assert len(chunks) >= 1
    assert any(c.choices[0].delta.content == "Here's your order!" for c in chunks)

    # Verify tool_calls were attached to the saved message body
    assert message_repo.saved_message_body is not None
    assert "tool_calls" in message_repo.saved_message_body
    assert len(message_repo.saved_message_body["tool_calls"]) == 2
    assert (
        message_repo.saved_message_body["tool_calls"][0]["payload"]["tool_name"]
        == "lookup_menu"
    )
    assert (
        message_repo.saved_message_body["tool_calls"][1]["payload"]["tool_name"]
        == "place_order"
    )
    assert collected_sms_events == [
        sms_followup_event,
        {
            "type": _implementation.BRIDGE_STREAM_EVENT_TYPE,
            "kind": _implementation.BRIDGE_STREAM_EVENT_KIND_TOOL_OUTPUT,
        },
    ]
    assert message_repo.saved_conversation_id is not None
    assert len(append_calls) == 3
    assert (
        str(message_repo.saved_conversation_id),
        tool_events[1]["payload"],
    ) in append_calls
    assert (
        str(message_repo.saved_conversation_id),
        tool_events[3]["payload"],
    ) in append_calls
    assert (
        str(message_repo.saved_conversation_id),
        prefetch_event["payload"],
    ) in append_calls


@pytest.mark.asyncio
async def test_streaming_no_events_no_tool_calls_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When no events are emitted, the saved message body has no tool_calls key."""
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
        timezone="America/Los_Angeles",
        name="test-project",
    )

    @asynccontextmanager
    async def _fake_trace_async_block(
        name: str,
        resource: str | None = None,
        service: str | None = None,
        tags: dict | None = None,
    ):  # type: ignore[no-untyped-def]
        yield None

    async def _fake_get_project_async(session, message):  # type: ignore[no-untyped-def]
        return project

    async def _fake_get_user_async(session, project, message):  # type: ignore[no-untyped-def]
        return user, False

    async def _fake_construct_agent_spec(**kwargs):  # type: ignore[no-untyped-def]
        return SimpleNamespace()

    class _NoEventStreamPalAgent:
        def __init__(self, spec=None):  # type: ignore[no-untyped-def]
            self.spec = spec

        async def run(
            self,
            pal_input: object,
            stream: bool = False,
            **_kwargs: Any,
        ) -> object:
            async def _stream():  # type: ignore[no-untyped-def]
                yield SimpleNamespace(content="Just a normal reply")

            return _stream()

    async def _fake_query_history_messages(*args, **kwargs):  # type: ignore[no-untyped-def]
        return []

    fake_session = AsyncMock()
    fake_session.commit = AsyncMock()
    fake_session.rollback = AsyncMock()

    monkeypatch.setattr(_implementation, "trace_async_block", _fake_trace_async_block)
    monkeypatch.setattr(
        _implementation.db, "MessageRepositoryAsync", lambda session: message_repo
    )
    monkeypatch.setattr(
        _implementation.db, "AgentRepositoryAsync", lambda session: agent_repo
    )
    monkeypatch.setattr(
        _implementation.project_service,
        "get_project_async",
        _fake_get_project_async,
    )
    monkeypatch.setattr(
        _implementation.user_service, "get_user_async", _fake_get_user_async
    )
    monkeypatch.setattr(
        _implementation.agent_service,
        "construct_agent_spec",
        _fake_construct_agent_spec,
    )
    monkeypatch.setattr(_implementation, "PalAgent", _NoEventStreamPalAgent)
    monkeypatch.setattr(
        _implementation, "query_history_messages", _fake_query_history_messages
    )
    monkeypatch.setattr(_implementation, "record_duration", lambda *a, **kw: None)

    message = Message(
        author_type=AuthorType.USER,
        sender_identifier="+15550001111",
        recipient_identifier="+15550002222",
        channel=Channel.VOICE,
        text=TextObject(body="Hello"),
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
    assert message_repo.saved_message_body is not None
    assert "tool_calls" not in message_repo.saved_message_body


# ---------------------------------------------------------------------------
# Non-streaming path test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_nonstreaming_tool_call_events_attached_to_first_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tool call events from non-streaming output are attached to the first saved message."""
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
        timezone="America/Los_Angeles",
        name="test-project",
    )

    async def _fake_get_project_async(session, message):  # type: ignore[no-untyped-def]
        return project

    async def _fake_get_user_async(session, project, message):  # type: ignore[no-untyped-def]
        return user, False

    async def _fake_construct_agent_spec(**kwargs):  # type: ignore[no-untyped-def]
        return SimpleNamespace()

    tool_events = [
        {
            "type": "tool_call",
            "payload": {
                "tool_name": "check_hours",
                "arguments": {"store_id": "123"},
                "result": '{"open": true}',
            },
        },
        {
            "type": "tool_result_cache",
            "payload": {
                "schema": "previous_tool_result.v1",
                "tool_name": "check_hours",
                "raw_result": '{"open": true}',
                "captured_at": "2026-06-22T20:00:00Z",
            },
        },
    ]
    prefetch_event = {
        "type": "tool_result_cache",
        "payload": {
            "schema": "previous_tool_result.v1",
            "tool_name": "toast_wait_time_prefetch_v1",
            "raw_result": '{"takeout_minutes":15}',
            "captured_at": "2026-06-22T20:00:01Z",
        },
    }
    captured_prefetch_sinks: list[Any] = []
    append_calls: list[tuple[str, dict[str, Any]]] = []

    async def _fake_append_tool_result(
        conversation_id: str, payload: dict[str, Any]
    ) -> None:
        append_calls.append((conversation_id, payload))

    class _EventPalAgent:
        def __init__(self, spec=None):  # type: ignore[no-untyped-def]
            self.spec = spec

        async def run(
            self,
            pal_input: object,
            stream: bool = False,
            *,
            prefetch_result_sink: Any | None = None,
        ) -> object:
            captured_prefetch_sinks.append(prefetch_result_sink)
            return SimpleNamespace(
                content="We are open!",
                escalated=False,
                closing_conversation=False,
                events=tool_events,
            )

    async def _fake_query_history_messages(*args, **kwargs):  # type: ignore[no-untyped-def]
        return []

    async def _fake_fingerprint_conversation(**kwargs: Any) -> None:
        return None

    fake_session = AsyncMock()
    fake_session.refresh = AsyncMock()

    monkeypatch.setattr(
        _implementation.db, "MessageRepositoryAsync", lambda session: message_repo
    )
    monkeypatch.setattr(
        _implementation.db, "AgentRepositoryAsync", lambda session: agent_repo
    )
    monkeypatch.setattr(
        _implementation.project_service,
        "get_project_async",
        _fake_get_project_async,
    )
    monkeypatch.setattr(
        _implementation.user_service, "get_user_async", _fake_get_user_async
    )
    monkeypatch.setattr(
        _implementation.agent_service,
        "construct_agent_spec",
        _fake_construct_agent_spec,
    )
    monkeypatch.setattr(_implementation, "PalAgent", _EventPalAgent)
    monkeypatch.setattr(
        _implementation, "query_history_messages", _fake_query_history_messages
    )
    monkeypatch.setattr(_implementation, "record_duration", lambda *a, **kw: None)
    monkeypatch.setattr(
        _implementation,
        "append_tool_result",
        _fake_append_tool_result,
    )
    monkeypatch.setattr(
        _implementation,
        "_fingerprint_conversation",
        _fake_fingerprint_conversation,
    )
    _implementation._background_tasks.clear()

    message = Message(
        author_type=AuthorType.USER,
        sender_identifier="+15550001111",
        recipient_identifier="+15550002222",
        channel=Channel.VOICE,
        text=TextObject(body="Are you open?"),
        metadata=Metadata(testing=True),
    )

    result = await _implementation.get_chat_response_async(
        session=fake_session,
        message=message,
        request_context=RequestContext(),
    )
    assert len(captured_prefetch_sinks) == 1
    assert callable(captured_prefetch_sinks[0])
    captured_prefetch_sinks[0](prefetch_event)
    await _drain_background_tasks(_implementation)

    # Verify response was returned
    assert len(result) > 0

    # Find the agent response message (skip the user request message saved first)
    agent_messages = [
        m
        for m in message_repo.created_messages
        if m["message_body"].get("author_type") == "agent"
    ]
    assert len(agent_messages) >= 1
    first_agent_body = agent_messages[0]["message_body"]
    assert "tool_calls" in first_agent_body
    assert len(first_agent_body["tool_calls"]) == 1
    assert first_agent_body["tool_calls"][0]["payload"]["tool_name"] == "check_hours"
    assert len(append_calls) == 2
    assert (
        str(message_repo.request_conversation_id),
        tool_events[1]["payload"],
    ) in append_calls
    assert (
        str(message_repo.request_conversation_id),
        prefetch_event["payload"],
    ) in append_calls
