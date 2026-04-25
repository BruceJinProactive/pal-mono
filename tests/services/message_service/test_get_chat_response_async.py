import sys
import uuid
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
                return SimpleNamespace(content="test response")

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
            return SimpleNamespace(content="test response")

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
        self.saved_messages = []

    async def create_message(self, **kwargs):
        self.created_message_kwargs = kwargs
        return SimpleNamespace(conversation_id=uuid.uuid4())

    async def add_message_to_conversation(self, conversation_id, message_body):
        self.saved_messages.append(
            {"conversation_id": conversation_id, "body": message_body}
        )


class _FakeConversationRepo:
    async def get_conversation_by_id(self, conversation_id):
        return SimpleNamespace(id=conversation_id, status="active")


class _FakeAgentRepo:
    async def get_agent(self, agent_id):
        return SimpleNamespace(language=None)


@pytest.mark.asyncio
async def test_get_chat_response_async_captures_project_attributes_early(monkeypatch):
    """
    Test that get_chat_response_async captures project attributes (id, name, agent_id,
    account_id, timezone) early to avoid lazy-loading issues after async boundaries.
    """
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_agent_shims_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)
    from services.message_service import _implementation

    message_repo = _FakeMessageRepo()
    conversation_repo = _FakeConversationRepo()
    agent_repo = _FakeAgentRepo()

    user = SimpleNamespace(id=uuid.uuid4())
    project = SimpleNamespace(
        id=uuid.uuid4(),
        name="test-project",
        account_id=uuid.uuid4(),
        raw_config={"use_pal_agents": True},
        agent_id=uuid.uuid4(),
        timezone="America/Los_Angeles",
        account=SimpleNamespace(name="test-account"),
    )

    async def _fake_get_project_async(session, message):
        return project

    async def _fake_get_user_async(session, project, message):
        return user, False

    async def _fake_construct_agent_spec(**kwargs):
        # Verify that project_id, not project.id, is being passed
        assert "project_id" in kwargs
        assert kwargs["project_id"] == project.id
        return SimpleNamespace()

    captured_runtime_contexts = []

    class _TestPalAgent:
        def __init__(self, spec=None):
            self.spec = spec

        async def run(self, pal_input, stream=False):
            # Capture the runtime context to verify correct attributes are passed
            captured_runtime_contexts.append(pal_input.runtime_context)
            return SimpleNamespace(
                content="test response",
                escalated=False,
                closing_conversation=False,
            )

    async def _fake_query_history_messages(*args, **kwargs):
        return []

    monkeypatch.setattr(
        _implementation.db, "MessageRepositoryAsync", lambda session: message_repo
    )
    monkeypatch.setattr(
        _implementation.db,
        "ConversationRepositoryAsync",
        lambda session: conversation_repo,
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
    monkeypatch.setattr(_implementation, "PalAgent", _TestPalAgent)
    monkeypatch.setattr(
        _implementation, "query_history_messages", _fake_query_history_messages
    )
    monkeypatch.setattr(
        _implementation, "send_dd_histogram_metrics", lambda *a, **kw: None
    )

    session = AsyncMock()
    session.refresh = AsyncMock()
    message = Message(
        author_type=AuthorType.USER,
        sender_identifier="+15550001111",
        recipient_identifier="+15550002222",
        channel=Channel.SMS,
        text=TextObject(body="Test message"),
        metadata=Metadata(testing=True),
    )

    result = await _implementation.get_chat_response_async(
        session=session,
        message=message,
        request_context=RequestContext(),
    )

    # Verify the function completed successfully
    assert len(result) > 0

    # Verify that RuntimeContext received the captured project attributes
    assert len(captured_runtime_contexts) == 1
    rc = captured_runtime_contexts[0]
    assert rc.project_id == str(project.id)
    assert rc.account_id == str(project.account_id)
    assert rc.timezone == project.timezone
    assert rc.agent_id == str(project.agent_id)


@pytest.mark.asyncio
async def test_get_chat_response_async_legacy_path_uses_captured_attributes(
    monkeypatch,
):
    """
    Test that get_chat_response_async uses captured project attributes in legacy (non-pal-agents) path.
    """
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_agent_shims_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)
    from services.message_service import _implementation

    message_repo = _FakeMessageRepo()
    conversation_repo = _FakeConversationRepo()
    agent_repo = _FakeAgentRepo()

    user = SimpleNamespace(id=uuid.uuid4())
    project = SimpleNamespace(
        id=uuid.uuid4(),
        name="test-project",
        account_id=uuid.uuid4(),
        raw_config={"use_pal_agents": False},  # Legacy path
        agent_id=uuid.uuid4(),
        timezone="America/New_York",
        account=SimpleNamespace(name="test-account"),
    )

    async def _fake_get_project_async(session, message):
        return project

    async def _fake_get_user_async(session, project, message):
        return user, False

    async def _fake_construct_agent_config(**kwargs):
        return SimpleNamespace(stream=False)

    class _TestAgent:
        def __init__(self, config):
            self.config = config

        async def arun(self, _input):
            return SimpleNamespace(
                content="legacy response",
                escalated=False,
                closing_conversation=False,
            )

    async def _fake_get_agent_input_from_message(**kwargs):
        return SimpleNamespace(content="input")

    async def _fake_query_history_messages(*args, **kwargs):
        return []

    monkeypatch.setattr(
        _implementation.db, "MessageRepositoryAsync", lambda session: message_repo
    )
    monkeypatch.setattr(
        _implementation.db,
        "ConversationRepositoryAsync",
        lambda session: conversation_repo,
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
    monkeypatch.setattr(_implementation, "Agent", _TestAgent)
    monkeypatch.setattr(
        _implementation._utils,
        "get_agent_input_from_message",
        _fake_get_agent_input_from_message,
    )
    monkeypatch.setattr(
        _implementation, "query_history_messages", _fake_query_history_messages
    )
    monkeypatch.setattr(
        _implementation, "send_dd_histogram_metrics", lambda *a, **kw: None
    )

    session = AsyncMock()
    session.refresh = AsyncMock()
    message = Message(
        author_type=AuthorType.USER,
        sender_identifier="+15550001111",
        recipient_identifier="+15550002222",
        channel=Channel.SMS,
        text=TextObject(body="Test message"),
        metadata=Metadata(testing=True),
    )

    result = await _implementation.get_chat_response_async(
        session=session,
        message=message,
        request_context=RequestContext(),
    )

    # Verify the function completed successfully with legacy agent
    assert len(result) > 0

    # Verify the response message has the expected structure
    response_message = result[0]
    assert response_message.author_type == AuthorType.AGENT
    assert response_message.metadata is not None
    assert response_message.metadata.project_name == "test-project"
    assert response_message.text is not None
    assert response_message.text.body == "legacy response"
