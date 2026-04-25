import asyncio
import json
import os
from importlib import import_module
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.responses import StreamingResponse

from api.schemas.chat.chat import ChatRequest
from api.schemas.chat.message import AuthorType, Message, Metadata, TextObject
from db.tables.types import Channel
from tests.services.message_service.test_get_chat_response_stream import (
    _install_agent_shims_if_needed,
    _install_knowledge_shim_if_needed,
    _install_services_shims_if_needed,
)
from utils.request_context import RequestContext


def _set_required_env() -> None:
    os.environ.setdefault("db_host", "localhost")
    os.environ.setdefault("db_port", "5432")
    os.environ.setdefault("db_user", "test")
    os.environ.setdefault("db_pass", "test")
    os.environ.setdefault("db_database", "test")
    os.environ.setdefault("AWS_ASSET_BUCKET_NAME", "test-bucket")


def _cancelled_async_iterator():
    async def _stream():
        if False:
            yield None
        raise asyncio.CancelledError()

    return _stream()


def _prepare_chat_import(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required_env()
    _install_knowledge_shim_if_needed(monkeypatch)
    _install_agent_shims_if_needed(monkeypatch)
    _install_services_shims_if_needed(monkeypatch)
    monkeypatch.delitem(
        __import__("sys").modules, "api.routes.chat.chat", raising=False
    )
    monkeypatch.delitem(
        __import__("sys").modules, "api.routes.chat.chat_completions", raising=False
    )
    monkeypatch.delitem(__import__("sys").modules, "api.routes.chat", raising=False)


class _FakeSessionContext:
    def __init__(self):
        self.session = AsyncMock()
        self.exited = False

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        self.exited = True
        return False


def _make_chat_request(
    *,
    stream: bool = False,
    relay_response: bool = False,
    testing: bool = True,
    channel: Channel = Channel.SMS,
) -> ChatRequest:
    return ChatRequest(
        message=Message(
            author_type=AuthorType.USER,
            sender_identifier="+15550001111",
            recipient_identifier="+15550002222",
            channel=channel,
            text=TextObject(body="Hello"),
            metadata=Metadata(testing=testing),
        ),
        relay_response=relay_response,
        stream=stream,
    )


@pytest.mark.asyncio
async def test_chat_stream_cancelled_error_returns_cleanly(monkeypatch):
    _prepare_chat_import(monkeypatch)
    chat_module = import_module("api.routes.chat.chat")

    async def _fake_get_chat_response_stream(**kwargs):
        return _cancelled_async_iterator()

    monkeypatch.setattr(
        chat_module, "get_chat_response_stream", _fake_get_chat_response_stream
    )
    monkeypatch.setattr(chat_module, "set_testing_mode", lambda testing: None)
    _mock_span = MagicMock()
    _mock_span.is_recording.return_value = False
    monkeypatch.setattr(chat_module.trace, "get_current_span", lambda: _mock_span)

    request = _make_chat_request(stream=True)

    response = await chat_module.chat(request=request, session=AsyncMock())
    assert isinstance(response, StreamingResponse)

    emitted = [chunk async for chunk in response.body_iterator]
    assert emitted == []


@pytest.mark.asyncio
async def test_chat_stream_without_injected_session_closes_managed_session(monkeypatch):
    _prepare_chat_import(monkeypatch)
    chat_module = import_module("api.routes.chat.chat")
    session_ctx = _FakeSessionContext()

    async def _fake_get_chat_response_stream(**kwargs):
        assert kwargs["session"] is session_ctx.session
        return _cancelled_async_iterator()

    monkeypatch.setattr(
        chat_module, "get_chat_response_stream", _fake_get_chat_response_stream
    )
    monkeypatch.setattr(chat_module, "set_testing_mode", lambda testing: None)
    _mock_span = MagicMock()
    _mock_span.is_recording.return_value = False
    monkeypatch.setattr(chat_module.trace, "get_current_span", lambda: _mock_span)
    monkeypatch.setattr(chat_module, "AsyncSessionLocal", lambda: session_ctx)

    request = _make_chat_request(stream=True)

    response = await chat_module.chat(request=request)
    assert isinstance(response, StreamingResponse)

    emitted = [chunk async for chunk in response.body_iterator]
    assert emitted == []
    assert session_ctx.exited is True


@pytest.mark.asyncio
async def test_chat_managed_session_rolls_back_on_error(monkeypatch):
    _prepare_chat_import(monkeypatch)
    chat_module = import_module("api.routes.chat.chat")
    session_ctx = _FakeSessionContext()
    monkeypatch.setattr(chat_module, "AsyncSessionLocal", lambda: session_ctx)

    with pytest.raises(RuntimeError, match="boom"):
        async with chat_module._managed_session(None):
            raise RuntimeError("boom")

    session_ctx.session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_chat_endpoint_delegates_to_chat(monkeypatch):
    _prepare_chat_import(monkeypatch)
    chat_module = import_module("api.routes.chat.chat")
    request = _make_chat_request()
    expected = object()
    mock_chat = AsyncMock(return_value=expected)
    monkeypatch.setattr(chat_module, "chat", mock_chat)

    result = await chat_module.chat_endpoint(request)

    assert result is expected
    mock_chat.assert_awaited_once_with(request)


@pytest.mark.asyncio
async def test_chat_stream_formats_supported_chunks_and_done(monkeypatch):
    _prepare_chat_import(monkeypatch)
    chat_module = import_module("api.routes.chat.chat")

    class _FakeRunResponse:
        def __init__(self, content: str):
            self._content = content

        def get_content_as_string(self) -> str:
            return self._content

    async def _fake_stream():
        yield _FakeRunResponse("hello")
        yield ("world", "ignored")
        yield 7
        yield object()

    async def _fake_get_chat_response_stream(**kwargs):
        return _fake_stream()

    mock_warning = MagicMock()
    monkeypatch.setattr(
        chat_module, "get_chat_response_stream", _fake_get_chat_response_stream
    )
    monkeypatch.setattr(chat_module, "RunResponse", _FakeRunResponse)
    monkeypatch.setattr(chat_module, "set_testing_mode", lambda testing: None)
    _mock_span = MagicMock()
    _mock_span.is_recording.return_value = False
    monkeypatch.setattr(chat_module.trace, "get_current_span", lambda: _mock_span)
    monkeypatch.setattr(chat_module.logger, "warning", mock_warning)

    response = await chat_module.chat(
        request=_make_chat_request(stream=True), session=AsyncMock()
    )

    emitted = [chunk async for chunk in response.body_iterator]
    assert emitted == [
        "data: hello\n\n",
        "data: world\n\n",
        "data: 7\n\n",
        "data: [DONE]\n\n",
    ]
    mock_warning.assert_called_once()


@pytest.mark.asyncio
async def test_chat_stream_without_upstream_stream_still_emits_done(monkeypatch):
    _prepare_chat_import(monkeypatch)
    chat_module = import_module("api.routes.chat.chat")

    async def _fake_get_chat_response_stream(**kwargs):
        return None

    monkeypatch.setattr(
        chat_module, "get_chat_response_stream", _fake_get_chat_response_stream
    )
    monkeypatch.setattr(chat_module, "set_testing_mode", lambda testing: None)
    _mock_span = MagicMock()
    _mock_span.is_recording.return_value = False
    monkeypatch.setattr(chat_module.trace, "get_current_span", lambda: _mock_span)

    response = await chat_module.chat(
        request=_make_chat_request(stream=True), session=AsyncMock()
    )

    emitted = [chunk async for chunk in response.body_iterator]
    assert emitted == ["data: [DONE]\n\n"]


@pytest.mark.asyncio
async def test_chat_stream_errors_yield_error_marker(monkeypatch):
    _prepare_chat_import(monkeypatch)
    chat_module = import_module("api.routes.chat.chat")

    async def _failing_stream():
        raise RuntimeError("stream exploded")
        if False:
            yield None

    async def _fake_get_chat_response_stream(**kwargs):
        return _failing_stream()

    mock_error = MagicMock()
    monkeypatch.setattr(
        chat_module, "get_chat_response_stream", _fake_get_chat_response_stream
    )
    monkeypatch.setattr(chat_module, "set_testing_mode", lambda testing: None)
    _mock_span = MagicMock()
    _mock_span.is_recording.return_value = False
    monkeypatch.setattr(chat_module.trace, "get_current_span", lambda: _mock_span)
    monkeypatch.setattr(chat_module.logger, "error", mock_error)

    response = await chat_module.chat(
        request=_make_chat_request(stream=True), session=AsyncMock()
    )

    emitted = [chunk async for chunk in response.body_iterator]
    assert emitted == [
        "data: [ERROR] An error occurred while streaming the response.\n\n"
    ]
    mock_error.assert_called_once()


@pytest.mark.asyncio
async def test_chat_non_streaming_returns_messages_with_active_session(monkeypatch):
    _prepare_chat_import(monkeypatch)
    chat_module = import_module("api.routes.chat.chat")
    session = AsyncMock()
    response_message = Message(
        author_type=AuthorType.AGENT,
        sender_identifier="+15550002222",
        recipient_identifier="+15550001111",
        channel=Channel.SMS,
        text=TextObject(body="Hi there"),
        metadata=Metadata(testing=True),
    )

    async def _fake_get_chat_response_async(**kwargs):
        assert kwargs["session"] is session
        return [response_message]

    monkeypatch.setattr(
        chat_module, "get_chat_response_async", _fake_get_chat_response_async
    )
    monkeypatch.setattr(chat_module, "set_testing_mode", lambda testing: None)
    _mock_span = MagicMock()
    _mock_span.is_recording.return_value = False
    monkeypatch.setattr(chat_module.trace, "get_current_span", lambda: _mock_span)

    response = await chat_module.chat(request=_make_chat_request(), session=session)

    assert response.status == "success"
    assert response.messages == [response_message]


@pytest.mark.asyncio
async def test_chat_completions_stream_cancelled_error_returns_cleanly(monkeypatch):
    _prepare_chat_import(monkeypatch)
    chat_completions_module = import_module("api.routes.chat.chat_completions")

    async def _fake_get_chat_response_stream(**kwargs):
        return _cancelled_async_iterator()

    class _IdentityFilter:
        def filter_content(self, content):
            return content

    monkeypatch.setattr(
        chat_completions_module,
        "get_chat_response_stream",
        _fake_get_chat_response_stream,
    )
    monkeypatch.setattr(
        chat_completions_module,
        "send_dd_histogram_metrics",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        chat_completions_module,
        "create_url_filter",
        lambda: _IdentityFilter(),
    )

    model = json.dumps(
        {
            "sender_identifier": "+15550001111",
            "recipient_identifier": "+15550002222",
            "call_id": "call-123",
        }
    )
    request = chat_completions_module.ChatCompletionRequest(
        model=model,
        message="Hello there",
        stream=True,
    )

    response = await chat_completions_module.chat_completions_agno(
        request=request,
        model=model,
        request_context=RequestContext(),
        session=AsyncMock(),
    )
    assert isinstance(response, StreamingResponse)

    emitted = [chunk async for chunk in response.body_iterator]
    assert emitted == []


@pytest.mark.asyncio
async def test_chat_completions_without_injected_session_closes_managed_session(
    monkeypatch,
):
    _prepare_chat_import(monkeypatch)
    chat_completions_module = import_module("api.routes.chat.chat_completions")
    session_ctx = _FakeSessionContext()

    async def _fake_get_chat_response_stream(**kwargs):
        assert kwargs["session"] is session_ctx.session
        return _cancelled_async_iterator()

    class _IdentityFilter:
        def filter_content(self, content):
            return content

    monkeypatch.setattr(
        chat_completions_module,
        "get_chat_response_stream",
        _fake_get_chat_response_stream,
    )
    monkeypatch.setattr(
        chat_completions_module,
        "send_dd_histogram_metrics",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        chat_completions_module,
        "create_url_filter",
        lambda: _IdentityFilter(),
    )
    monkeypatch.setattr("db.session.AsyncSessionLocal", lambda: session_ctx)

    model = json.dumps(
        {
            "sender_identifier": "+15550001111",
            "recipient_identifier": "+15550002222",
            "call_id": "call-123",
        }
    )
    request = chat_completions_module.ChatCompletionRequest(
        model=model,
        message="Hello there",
        stream=True,
    )

    response = await chat_completions_module.chat_completions_agno(
        request=request,
        model=model,
        request_context=RequestContext(),
    )
    assert isinstance(response, StreamingResponse)

    emitted = [chunk async for chunk in response.body_iterator]
    assert emitted == []
    assert session_ctx.exited is True
