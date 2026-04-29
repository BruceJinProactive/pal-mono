"""S2: SSE Streaming Session Lifecycle.

Tests that streaming endpoints use _managed_session() (ADR-019),
yield proper SSE format with [DONE] terminator, and handle errors gracefully.
"""

import asyncio
from typing import AsyncIterator
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from api.schemas.chat.chat import ChatRequest
from api.schemas.chat.message import AuthorType, Message, TextObject, Type
from db.tables.types import Channel


def _build_chat_request(
    sender: str, recipient: str, body: str, stream: bool = True
) -> dict[str, object]:
    """Build a ChatRequest-compatible dict for POST /v1/chat/."""
    msg = Message(
        author_type=AuthorType.USER,
        sender_identifier=sender,
        recipient_identifier=recipient,
        channel=Channel.API,
        type=Type.TEXT,
        text=TextObject(body=body),
    )
    return ChatRequest(message=msg, stream=stream).model_dump(mode="json")


async def collect_sse_events(response: httpx.Response) -> list[str]:
    """Collect SSE data events from a streaming response."""
    events: list[str] = []
    async for line in response.aiter_lines():
        if line.startswith("data: "):
            events.append(line[6:])
    return events


@pytest.mark.integration
class TestStreamingLifecycle:
    async def test_stream_yields_done_terminator(
        self,
        client: httpx.AsyncClient,
        world: object,
        patch_async_session_local: None,
    ) -> None:
        """Happy path: streaming response ends with [DONE]."""

        async def fake_stream(*args: object, **kwargs: object) -> AsyncIterator[str]:
            yield "Hello "
            yield "world!"

        with (
            patch(
                "api.routes.chat.chat.get_chat_response_stream",
                new_callable=AsyncMock,
                return_value=fake_stream(),
            ),
            patch("api.routes.chat.chat.send_messages", new_callable=AsyncMock),
            patch("api.routes.chat.chat.set_testing_mode"),
        ):
            async with client.stream(
                "POST",
                "/v1/chat/",
                json=_build_chat_request(
                    sender="test-user@example.com",
                    recipient="+15559990001",
                    body="Hi there",
                ),
            ) as response:
                assert response.status_code == 200
                events = await collect_sse_events(response)

        assert len(events) >= 2
        assert events[-1] == "[DONE]"

    async def test_stream_error_yields_error_event(
        self,
        client: httpx.AsyncClient,
        world: object,
        patch_async_session_local: None,
    ) -> None:
        """Mid-stream failure yields [ERROR] event."""

        async def failing_stream(*args: object, **kwargs: object) -> AsyncIterator[str]:
            yield "partial "
            raise asyncio.TimeoutError("LLM timed out")

        with (
            patch(
                "api.routes.chat.chat.get_chat_response_stream",
                new_callable=AsyncMock,
                return_value=failing_stream(),
            ),
            patch("api.routes.chat.chat.send_messages", new_callable=AsyncMock),
            patch("api.routes.chat.chat.set_testing_mode"),
        ):
            async with client.stream(
                "POST",
                "/v1/chat/",
                json=_build_chat_request(
                    sender="test-user@example.com",
                    recipient="+15559990001",
                    body="Hi there",
                ),
            ) as response:
                assert response.status_code == 200
                events = await collect_sse_events(response)

        # Should contain an error event
        error_events = [e for e in events if "[ERROR]" in e]
        assert len(error_events) >= 1

    async def test_non_stream_returns_json(
        self,
        client: httpx.AsyncClient,
        world: object,
        patch_async_session_local: None,
    ) -> None:
        """Non-streaming request returns JSON ChatResponse."""
        with (
            patch(
                "api.routes.chat.chat.get_chat_response_async",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("api.routes.chat.chat.send_messages", new_callable=AsyncMock),
            patch("api.routes.chat.chat.set_testing_mode"),
        ):
            response = await client.post(
                "/v1/chat/",
                json=_build_chat_request(
                    sender="test-user@example.com",
                    recipient="+15559990001",
                    body="Hi there",
                    stream=False,
                ),
            )

        assert response.status_code == 200

    async def test_managed_session_not_depends(self) -> None:
        """ADR-019: chat() signature accepts session as optional, not Depends."""
        import inspect

        from api.routes.chat.chat import chat

        sig = inspect.signature(chat)
        session_param = sig.parameters.get("session")
        assert session_param is not None
        # Default should be None, not a Depends() instance
        assert session_param.default is None
