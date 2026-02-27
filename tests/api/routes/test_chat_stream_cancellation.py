import asyncio
import json
import os
from importlib import import_module
from unittest.mock import AsyncMock

import pytest
from fastapi.responses import StreamingResponse

from api.schemas.chat.chat import ChatRequest
from api.schemas.chat.message import AuthorType, Message, Metadata, TextObject
from db.tables.types import Channel
from tests.message_service_test.test_get_chat_response_stream import (
    _install_agent_shims_if_needed,
    _install_ddtrace_llmobs_shim_if_needed,
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
    _install_ddtrace_llmobs_shim_if_needed(monkeypatch)
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
    monkeypatch.setattr(chat_module.tracer, "current_span", lambda: None)

    request = ChatRequest(
        message=Message(
            author_type=AuthorType.USER,
            sender_identifier="+15550001111",
            recipient_identifier="+15550002222",
            channel=Channel.SMS,
            text=TextObject(body="Hello"),
            metadata=Metadata(testing=True),
        ),
        stream=True,
    )

    response = await chat_module.chat(request=request, session=AsyncMock())
    assert isinstance(response, StreamingResponse)

    emitted = [chunk async for chunk in response.body_iterator]
    assert emitted == []


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
