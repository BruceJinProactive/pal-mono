"""Test order persistence from streaming chunks."""

import sys
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.schemas.chat.message import AuthorType, Message, Metadata, TextObject
from db.tables.types import Channel, IntegrationProvider
from utils.request_context import RequestContext


def _ensure_package_module(
    monkeypatch: pytest.MonkeyPatch, name: str, module: ModuleType | None = None
) -> ModuleType:
    pkg = module or ModuleType(name)
    if not hasattr(pkg, "__path__"):
        pkg.__path__ = []  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, name, pkg)
    return pkg


def _install_ddtrace_llmobs_shim_if_needed(monkeypatch: pytest.MonkeyPatch) -> None:
    try:
        import ddtrace.llmobs.decorators  # noqa: F401

        return
    except Exception:
        pass

    ddtrace_mod = sys.modules.get("ddtrace")
    if ddtrace_mod is None:
        ddtrace_mod = _ensure_package_module(monkeypatch, "ddtrace")
    else:
        _ensure_package_module(monkeypatch, "ddtrace", ddtrace_mod)

    llmobs_mod = ModuleType("ddtrace.llmobs")
    decorators_mod = ModuleType("ddtrace.llmobs.decorators")
    _ensure_package_module(monkeypatch, "ddtrace.llmobs", llmobs_mod)
    monkeypatch.setitem(sys.modules, "ddtrace.llmobs.decorators", decorators_mod)

    class _NoopLLMObs:
        @staticmethod
        def disable() -> None:
            return

        @staticmethod
        def enable(**kwargs) -> None:
            return

        @staticmethod
        def annotate(**kwargs) -> None:
            return

    def _noop_decorator(name=None):
        def _decorator(func):
            return func

        return _decorator

    llmobs_mod.LLMObs = _NoopLLMObs  # type: ignore[attr-defined]
    llmobs_mod.decorators = decorators_mod  # type: ignore[attr-defined]
    decorators_mod.agent = _noop_decorator  # type: ignore[attr-defined]
    decorators_mod.workflow = _noop_decorator  # type: ignore[attr-defined]
    decorators_mod.task = _noop_decorator  # type: ignore[attr-defined]
    decorators_mod.__getattr__ = lambda name: _noop_decorator  # type: ignore[attr-defined]


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


class _FakeOrderRepository:
    """Fake OrderRepository to capture order creation calls."""

    def __init__(self, session, auto_commit=True):
        self.session = session
        self.auto_commit = auto_commit
        self.created_orders = []

    def create_order(
        self,
        conversation_id,
        vendor=None,
        order_id=None,
        store_id=None,
        user_phone_number=None,
        tracking_link=None,
        status=None,
        fulfillment_strategy=None,
        subtotal=None,
        order_items=None,
        order_time=None,
        **kwargs,
    ):
        order_data = {
            "conversation_id": conversation_id,
            "vendor": vendor,
            "order_id": order_id,
            "store_id": store_id,
            "user_phone_number": user_phone_number,
            "tracking_link": tracking_link,
            "status": status,
            "fulfillment_strategy": fulfillment_strategy,
            "subtotal": subtotal,
            "order_items": order_items,
            "order_time": order_time,
        }
        self.created_orders.append(order_data)
        return SimpleNamespace(**order_data)


@pytest.mark.asyncio
async def test_order_details_persisted_to_database(monkeypatch):
    """Test that order_details from streaming chunk are persisted to the database."""
    _install_ddtrace_llmobs_shim_if_needed(monkeypatch)
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)
    from services.message_service import _implementation

    message_repo = _FakeMessageRepo()
    order_repo = None  # Will be set by the factory
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

    # Create a PalAgent that yields chunks with order_details
    class _OrderStreamPalAgent:
        def __init__(self, spec=None):
            self.spec = spec

        async def run(self, pal_input, stream=False):
            async def _stream():
                # First chunk: normal content
                yield SimpleNamespace(content="Your order has been placed!")

                # Second chunk: with order_details
                order_details = SimpleNamespace(
                    vendor="toast",
                    order_id="ORDER-123",
                    store_id="STORE-456",
                    user_phone_number="+15551234567",
                    tracking_link="https://example.com/track/ORDER-123",
                    status="pending",
                    fulfillment_strategy="pickup",
                    subtotal=25.50,
                    tax=2.55,
                    service_charge=1.25,
                    delivery_charge=0.0,
                    discount=0.0,
                    total=29.30,
                    order_items=[
                        {"name": "Burger", "quantity": 2, "price": 10.00},
                        {"name": "Fries", "quantity": 1, "price": 5.50},
                    ],
                    order_time="2024-03-14T12:00:00-07:00",
                )
                chunk_with_order = SimpleNamespace(
                    content="", order_details=order_details
                )
                yield chunk_with_order

                # Third chunk: more content
                yield SimpleNamespace(content=" Order ID: ORDER-123")

            return _stream()

    async def _fake_query_history_messages(*args, **kwargs):
        return []

    # Create a fake session with run_sync support
    fake_sync_session = MagicMock()
    fake_session = AsyncMock()
    fake_session.sync_session = fake_sync_session
    fake_session.commit = AsyncMock()
    fake_session.rollback = AsyncMock()

    # Mock run_sync to execute the function synchronously
    async def _fake_run_sync(func):
        func(fake_sync_session)

    fake_session.run_sync = _fake_run_sync

    # Factory function for OrderRepository
    def _fake_order_repository_factory(session, auto_commit=True):
        nonlocal order_repo
        order_repo = _FakeOrderRepository(session, auto_commit)
        return order_repo

    monkeypatch.setattr(_implementation, "trace_async_block", _fake_trace_async_block)
    monkeypatch.setattr(_implementation, "is_testing_mode", lambda: True)
    monkeypatch.setattr(_implementation.LLMObs, "disable", lambda: None)
    monkeypatch.setattr(
        _implementation.db, "MessageRepositoryAsync", lambda session: message_repo
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
    monkeypatch.setattr(_implementation, "PalAgent", _OrderStreamPalAgent)
    monkeypatch.setattr(
        _implementation, "query_history_messages", _fake_query_history_messages
    )
    monkeypatch.setattr(
        _implementation, "send_dd_histogram_metrics", lambda *a, **kw: None
    )
    monkeypatch.setattr(
        _implementation, "OrderRepository", _fake_order_repository_factory
    )

    message = Message(
        author_type=AuthorType.USER,
        sender_identifier="+15550001111",
        recipient_identifier="+15550002222",
        channel=Channel.VOICE,
        text=TextObject(body="I want to order a burger"),
        metadata=Metadata(testing=True),
    )

    # Collect all chunks
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
    assert chunks[0].choices[0].delta.content == "Your order has been placed!"

    # Verify that OrderRepository was created and order was persisted
    assert order_repo is not None, "OrderRepository should have been instantiated"
    assert len(order_repo.created_orders) == 1, "One order should have been created"

    # Verify order data
    created_order = order_repo.created_orders[0]
    assert created_order["vendor"] == IntegrationProvider.toast
    assert created_order["order_id"] == "ORDER-123"
    assert created_order["store_id"] == "STORE-456"
    assert created_order["user_phone_number"] == "+15551234567"
    assert created_order["tracking_link"] == "https://example.com/track/ORDER-123"
    assert created_order["status"] == "pending"
    assert created_order["fulfillment_strategy"] == "pickup"
    assert created_order["subtotal"] == Decimal("25.50")
    assert len(created_order["order_items"]) == 2
    assert created_order["order_items"][0]["name"] == "Burger"

    # Verify session.commit was called
    assert fake_session.commit.call_count == 1
    fake_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_order_details_error_handling(monkeypatch):
    """Test that order persistence errors are handled gracefully."""
    _install_ddtrace_llmobs_shim_if_needed(monkeypatch)
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)
    from services.message_service import _implementation

    message_repo = _FakeMessageRepo()
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

    class _OrderStreamPalAgent:
        def __init__(self, spec=None):
            self.spec = spec

        async def run(self, pal_input, stream=False):
            async def _stream():
                # Chunk with order_details
                order_details = SimpleNamespace(
                    vendor="toast",
                    order_id="ORDER-789",
                    store_id="STORE-456",
                    user_phone_number="+15551234567",
                    tracking_link="https://example.com/track/ORDER-789",
                    status="confirmed",
                    fulfillment_strategy="pickup",
                    subtotal=15.00,
                    tax=1.50,
                    service_charge=0.75,
                    delivery_charge=0.0,
                    discount=0.0,
                    total=17.25,
                    order_items=[{"name": "Pizza", "quantity": 1, "price": 15.00}],
                    order_time="2024-03-14T13:00:00-07:00",
                )
                yield SimpleNamespace(
                    content="Order placed!", order_details=order_details
                )

            return _stream()

    async def _fake_query_history_messages(*args, **kwargs):
        return []

    # OrderRepository that raises an error
    class _FailingOrderRepository:
        def __init__(self, session, auto_commit=True):
            self.session = session

        def create_order(self, **kwargs):
            raise Exception("Database connection error")

    fake_sync_session = MagicMock()
    fake_session = AsyncMock()
    fake_session.sync_session = fake_sync_session
    fake_session.commit = AsyncMock()
    fake_session.rollback = AsyncMock()

    # Mock run_sync to execute the function synchronously
    async def _fake_run_sync(func):
        func(fake_sync_session)

    fake_session.run_sync = _fake_run_sync

    monkeypatch.setattr(_implementation, "trace_async_block", _fake_trace_async_block)
    monkeypatch.setattr(_implementation, "is_testing_mode", lambda: True)
    monkeypatch.setattr(_implementation.LLMObs, "disable", lambda: None)
    monkeypatch.setattr(
        _implementation.db, "MessageRepositoryAsync", lambda session: message_repo
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
    monkeypatch.setattr(_implementation, "PalAgent", _OrderStreamPalAgent)
    monkeypatch.setattr(
        _implementation, "query_history_messages", _fake_query_history_messages
    )
    monkeypatch.setattr(
        _implementation, "send_dd_histogram_metrics", lambda *a, **kw: None
    )
    monkeypatch.setattr(_implementation, "OrderRepository", _FailingOrderRepository)

    message = Message(
        author_type=AuthorType.USER,
        sender_identifier="+15550001111",
        recipient_identifier="+15550002222",
        channel=Channel.VOICE,
        text=TextObject(body="I want to order a pizza"),
        metadata=Metadata(testing=True),
    )

    # Stream should continue even if order persistence fails
    chunks = [
        chunk
        async for chunk in _implementation.get_chat_response_stream(
            session=fake_session,
            message=message,
            request_context=RequestContext(),
        )
    ]

    # Verify chunks were still generated despite the error
    assert len(chunks) >= 1
    assert chunks[0].choices[0].delta.content == "Order placed!"

    # Verify session.rollback was called due to the error
    assert fake_session.rollback.call_count == 1
    fake_session.rollback.assert_called_once()
