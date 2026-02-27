# pyright: reportGeneralTypeIssues=false, reportAttributeAccessIssue=false
"""Tests for chat completions endpoint implementation.

Tests cover:
- Request content extraction from messages/message fields
- Caller info parsing from model string
- Chunk conversion to dict format
- Fallback chunk creation
- URL validation logic
- SMS URL sending with summarization
- Chat completions endpoint with streaming
- Error handling and validation
"""

import asyncio
import datetime
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException, status

from api.routes.chat.chat_completions import (
    ChatCompletionRequest,
    _convert_chunk_to_dict,
    _create_fallback_chunk,
    _extract_content_from_request,
    _parse_caller_info,
    _send_urls_via_sms,
    chat_completions_agno,
    is_invalid_url,
)
from api.schemas.chat.message import Broker
from db.tables.types import Channel
from utils.request_context import RequestContext

# ---------------------------------------------------------------------------
# Content Extraction Tests
# ---------------------------------------------------------------------------


class TestExtractContentFromRequest:
    """Test _extract_content_from_request() function."""

    def test_extract_from_message_field(self) -> None:
        """Extract content from 'message' field when present."""
        request = ChatCompletionRequest(
            model="test-model",
            message="Hello world",
            messages=[],
        )
        content = _extract_content_from_request(request)
        assert content == "Hello world"

    def test_extract_from_messages_array_single_user_message(self) -> None:
        """Extract content from messages array with single user message."""
        request = ChatCompletionRequest(
            model="test-model",
            messages=[
                {"role": "user", "content": "What's the weather?"},
            ],
        )
        content = _extract_content_from_request(request)
        assert content == "What's the weather?"

    def test_extract_from_messages_array_multiple_user_messages(self) -> None:
        """Extract last user message when multiple user messages exist."""
        request = ChatCompletionRequest(
            model="test-model",
            messages=[
                {"role": "user", "content": "First message"},
                {"role": "assistant", "content": "Response"},
                {"role": "user", "content": "Second message"},
            ],
        )
        content = _extract_content_from_request(request)
        assert content == "Second message"

    def test_extract_from_messages_no_user_messages(self) -> None:
        """Extract last message content when no user messages exist."""
        request = ChatCompletionRequest(
            model="test-model",
            messages=[
                {"role": "system", "content": "You are helpful"},
                {"role": "assistant", "content": "Hello there"},
            ],
        )
        content = _extract_content_from_request(request)
        assert content == "Hello there"

    def test_extract_raises_error_when_neither_field_provided(self) -> None:
        """Raise ValueError when neither message nor messages provided."""
        request = ChatCompletionRequest(
            model="test-model",
            message=None,
            messages=[],
        )
        with pytest.raises(
            ValueError, match="Either 'message' or 'messages' must be provided"
        ):
            _extract_content_from_request(request)

    def test_extract_prefers_messages_over_message(self) -> None:
        """Prefer messages array over message field when both present."""
        request = ChatCompletionRequest(
            model="test-model",
            message="Should be ignored",
            messages=[
                {"role": "user", "content": "Should be used"},
            ],
        )
        content = _extract_content_from_request(request)
        assert content == "Should be used"

    def test_extract_handles_empty_content(self) -> None:
        """Handle messages with empty content."""
        request = ChatCompletionRequest(
            model="test-model",
            messages=[
                {"role": "user", "content": ""},
            ],
        )
        content = _extract_content_from_request(request)
        assert content == ""

    def test_extract_handles_missing_content_field(self) -> None:
        """Handle messages without content field."""
        request = ChatCompletionRequest(
            model="test-model",
            messages=[
                {"role": "user"},
            ],
        )
        content = _extract_content_from_request(request)
        assert content == ""


# ---------------------------------------------------------------------------
# Caller Info Parsing Tests
# ---------------------------------------------------------------------------


class TestParseCallerInfo:
    """Test _parse_caller_info() function."""

    def test_parse_valid_json_with_all_fields(self) -> None:
        """Parse valid JSON with all fields."""
        model = json.dumps(
            {
                "sender_identifier": "+15551234567",
                "recipient_identifier": "+15557654321",
                "call_id": "call-123",
                "room_name": "room-abc",
                "participant_identity": "participant-xyz",
            }
        )
        sender, recipient, call_id, room_name, participant = _parse_caller_info(model)

        assert sender == "+15551234567"
        assert recipient == "+15557654321"
        assert call_id == "call-123"
        assert room_name == "room-abc"
        assert participant == "participant-xyz"

    def test_parse_valid_json_with_required_fields_only(self) -> None:
        """Parse valid JSON with only required fields."""
        model = json.dumps(
            {
                "sender_identifier": "user@example.com",
                "recipient_identifier": "agent-001",
            }
        )
        sender, recipient, call_id, room_name, participant = _parse_caller_info(model)

        assert sender == "user@example.com"
        assert recipient == "agent-001"
        assert call_id is None
        assert room_name is None
        assert participant is None

    def test_parse_missing_sender_uses_default(self) -> None:
        """Use default 'user' when sender_identifier missing."""
        model = json.dumps(
            {
                "recipient_identifier": "agent-001",
            }
        )
        sender, recipient, call_id, room_name, participant = _parse_caller_info(model)

        assert sender == "user"
        assert recipient == "agent-001"

    def test_parse_missing_recipient_uses_model_string(self) -> None:
        """Use model string when recipient_identifier missing."""
        model = json.dumps(
            {
                "sender_identifier": "user@example.com",
            }
        )
        sender, recipient, call_id, room_name, participant = _parse_caller_info(model)

        assert sender == "user@example.com"
        assert recipient == model  # Falls back to original model string

    def test_parse_missing_both_uses_defaults(self) -> None:
        """Use defaults when both identifiers missing."""
        model = json.dumps(
            {
                "call_id": "call-123",
            }
        )
        sender, recipient, call_id, room_name, participant = _parse_caller_info(model)

        assert sender == "user"
        assert recipient == model  # Falls back to model string
        assert call_id == "call-123"

    def test_parse_invalid_json_raises_exception(self) -> None:
        """Raise exception for invalid JSON."""
        model = "not valid json {"

        with pytest.raises(Exception, match="Error parsing model as JSON"):
            _parse_caller_info(model)

    def test_parse_non_string_raises_exception(self) -> None:
        """Raise exception for non-string, non-JSON types."""
        model = 12345  # type: ignore[arg-type]

        with pytest.raises(Exception, match="Error parsing model as JSON"):
            _parse_caller_info(model)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Chunk Conversion Tests
# ---------------------------------------------------------------------------


class TestConvertChunkToDict:
    """Test _convert_chunk_to_dict() function."""

    def test_convert_chunk_with_model_dump(self) -> None:
        """Convert chunk using model_dump() method when available."""
        chunk = SimpleNamespace()
        chunk.model_dump = lambda: {
            "id": "chatcmpl-123",
            "object": "chat.completion.chunk",
            "created": 1234567890,
            "model": "gpt-4",
            "choices": [{"index": 0, "delta": {"content": "Hello"}}],
        }

        result = _convert_chunk_to_dict(chunk)

        assert result["id"] == "chatcmpl-123"
        assert result["object"] == "chat.completion.chunk"
        assert result["created"] == 1234567890

    def test_convert_chunk_fallback_format(self) -> None:
        """Convert chunk using fallback dict format."""
        delta = SimpleNamespace(role="assistant", content="Hello")
        choice = SimpleNamespace(index=0, delta=delta, finish_reason="stop")
        chunk = SimpleNamespace(
            id="chatcmpl-123",
            object="chat.completion.chunk",
            created=1234567890,
            model="gpt-4",
            choices=[choice],
        )

        result = _convert_chunk_to_dict(chunk)

        assert result["id"] == "chatcmpl-123"
        assert result["object"] == "chat.completion.chunk"
        assert result["created"] == 1234567890
        assert result["model"] == "gpt-4"
        assert len(result["choices"]) == 1
        assert result["choices"][0]["index"] == 0
        assert result["choices"][0]["delta"]["role"] == "assistant"
        assert result["choices"][0]["delta"]["content"] == "Hello"
        assert result["choices"][0]["finish_reason"] == "stop"

    def test_convert_chunk_with_none_role(self) -> None:
        """Handle chunks with None role in delta."""
        delta = SimpleNamespace(content="Hello")
        choice = SimpleNamespace(index=0, delta=delta, finish_reason=None)
        chunk = SimpleNamespace(
            id="chatcmpl-123",
            object="chat.completion.chunk",
            created=1234567890,
            model="gpt-4",
            choices=[choice],
        )

        result = _convert_chunk_to_dict(chunk)

        assert result["choices"][0]["delta"]["role"] is None
        assert result["choices"][0]["delta"]["content"] == "Hello"

    def test_convert_chunk_multiple_choices(self) -> None:
        """Convert chunk with multiple choices."""
        delta1 = SimpleNamespace(role="assistant", content="Hello")
        delta2 = SimpleNamespace(role="assistant", content="Hi")
        choice1 = SimpleNamespace(index=0, delta=delta1, finish_reason=None)
        choice2 = SimpleNamespace(index=1, delta=delta2, finish_reason=None)
        chunk = SimpleNamespace(
            id="chatcmpl-123",
            object="chat.completion.chunk",
            created=1234567890,
            model="gpt-4",
            choices=[choice1, choice2],
        )

        result = _convert_chunk_to_dict(chunk)

        assert len(result["choices"]) == 2
        assert result["choices"][0]["index"] == 0
        assert result["choices"][1]["index"] == 1


# ---------------------------------------------------------------------------
# Fallback Chunk Creation Tests
# ---------------------------------------------------------------------------


class TestCreateFallbackChunk:
    """Test _create_fallback_chunk() function."""

    def test_create_fallback_chunk_structure(self) -> None:
        """Create fallback chunk with correct structure."""
        chunk = _create_fallback_chunk("gpt-4", "Error occurred")

        assert chunk["object"] == "chat.completion.chunk"
        assert chunk["model"] == "gpt-4"
        assert "id" in chunk
        assert chunk["id"].startswith("chatcmpl-")
        assert "created" in chunk
        assert isinstance(chunk["created"], int)
        assert len(chunk["choices"]) == 1
        assert chunk["choices"][0]["index"] == 0
        assert chunk["choices"][0]["delta"]["role"] == "assistant"
        assert chunk["choices"][0]["delta"]["content"] == "Error occurred"
        assert chunk["choices"][0]["finish_reason"] == "stop"

    def test_create_fallback_chunk_unique_ids(self) -> None:
        """Generate unique IDs for different fallback chunks."""
        chunk1 = _create_fallback_chunk("gpt-4", "Error 1")
        chunk2 = _create_fallback_chunk("gpt-4", "Error 2")

        assert chunk1["id"] != chunk2["id"]

    def test_create_fallback_chunk_timestamp(self) -> None:
        """Generate recent timestamp for fallback chunk."""
        before = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        chunk = _create_fallback_chunk("gpt-4", "Error")
        after = int(datetime.datetime.now(datetime.timezone.utc).timestamp())

        # Timestamp is converted to int, so allow for 1 second difference
        assert before <= chunk["created"] <= after + 1


# ---------------------------------------------------------------------------
# URL Validation Tests
# ---------------------------------------------------------------------------


class TestIsInvalidUrl:
    """Test is_invalid_url() function."""

    def test_valid_com_domain(self) -> None:
        """Valid .com domains should not be invalid."""
        assert is_invalid_url("example.com") is False
        assert is_invalid_url("google.com") is False

    def test_valid_org_domain(self) -> None:
        """Valid .org domains should not be invalid."""
        assert is_invalid_url("wikipedia.org") is False

    def test_valid_net_domain(self) -> None:
        """Valid .net domains should not be invalid."""
        assert is_invalid_url("example.net") is False

    def test_invalid_two_word_dot_pattern(self) -> None:
        """Two words with dot and invalid TLD should be invalid."""
        assert is_invalid_url("moment.It") is True
        assert is_invalid_url("word.Another") is True

    def test_valid_two_word_with_valid_extension(self) -> None:
        """Two words with valid extension should not be invalid."""
        assert is_invalid_url("my.app") is False
        assert is_invalid_url("test.dev") is False

    def test_url_with_subdomain(self) -> None:
        """URLs with subdomains should not be invalid."""
        assert is_invalid_url("api.example.com") is False
        assert is_invalid_url("www.test.org") is False

    def test_url_with_non_alphabetic_characters(self) -> None:
        """URLs with numbers or special chars should not be invalid."""
        assert is_invalid_url("example123.com") is False
        assert is_invalid_url("test-site.org") is False

    def test_single_word(self) -> None:
        """Single words should not be invalid."""
        assert is_invalid_url("example") is False

    def test_url_with_path(self) -> None:
        """URLs with paths should not be invalid."""
        assert is_invalid_url("example.com/path") is False


# ---------------------------------------------------------------------------
# SMS URL Sending Tests
# ---------------------------------------------------------------------------


class TestSendUrlsViaSms:
    """Test _send_urls_via_sms() function."""

    @pytest.mark.asyncio
    async def test_no_urls_sends_nothing(self) -> None:
        """Do not send SMS when no URLs found."""
        with patch("api.routes.chat.chat_completions.send_message") as mock_send:
            await _send_urls_via_sms(
                collected_content=["Hello world", "No links here"],
                sender_identifier="+15551234567",
                recipient_identifier="+15557654321",
            )

            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_urls_filtered_out(self) -> None:
        """Filter out invalid URLs like 'moment.It'."""
        with patch("api.routes.chat.chat_completions.send_message") as mock_send:
            await _send_urls_via_sms(
                collected_content=["Check out moment.It for details"],
                sender_identifier="+15551234567",
                recipient_identifier="+15557654321",
            )

            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_valid_url_triggers_sms(self) -> None:
        """Send SMS when valid URL found."""
        mock_response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="Your order is ready: [INSERT_URL_HERE]"
                    )
                )
            ]
        )

        with patch(
            "api.routes.chat.chat_completions.call_llm_default",
            return_value=mock_response,
        ):
            with patch(
                "api.routes.chat.chat_completions.send_message",
                return_value={"status": "sent"},
            ) as mock_send:
                await _send_urls_via_sms(
                    collected_content=["Order here: https://example.com/order"],
                    sender_identifier="+15551234567",
                    recipient_identifier="+15557654321",
                )

                mock_send.assert_called_once()
                call_args = mock_send.call_args[0][0]
                assert call_args.channel == Channel.SMS
                assert call_args.broker == Broker.TWILIO
                assert "https://example.com/order" in call_args.text.body

    @pytest.mark.asyncio
    async def test_multiple_urls_uses_first_only(self) -> None:
        """Use only first URL when multiple found."""
        mock_response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="Links: [INSERT_URL_HERE]")
                )
            ]
        )

        with patch(
            "api.routes.chat.chat_completions.call_llm_default",
            return_value=mock_response,
        ):
            with patch(
                "api.routes.chat.chat_completions.send_message",
                return_value={"status": "sent"},
            ) as mock_send:
                await _send_urls_via_sms(
                    collected_content=[
                        "Visit https://first.com and https://second.com"
                    ],
                    sender_identifier="+15551234567",
                    recipient_identifier="+15557654321",
                )

                mock_send.assert_called_once()
                call_args = mock_send.call_args[0][0]
                assert "https://first.com" in call_args.text.body
                assert "https://second.com" not in call_args.text.body

    @pytest.mark.asyncio
    async def test_llm_summarization_with_placeholder(self) -> None:
        """LLM generates summary with placeholder replaced by URL."""
        mock_response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="Your payment link: [INSERT_URL_HERE]"
                    )
                )
            ]
        )

        with patch(
            "api.routes.chat.chat_completions.call_llm_default",
            return_value=mock_response,
        ) as mock_llm:
            with patch(
                "api.routes.chat.chat_completions.send_message",
                return_value={"status": "sent"},
            ) as mock_send:
                await _send_urls_via_sms(
                    collected_content=["Pay now: https://pay.example.com/invoice"],
                    sender_identifier="+15551234567",
                    recipient_identifier="+15557654321",
                )

                # Verify LLM was called with correct prompt
                mock_llm.assert_called_once()
                call_args = mock_llm.call_args[1]
                assert "params" in call_args
                assert "messages" in call_args["params"]

                # Verify SMS sent with URL replacing placeholder
                mock_send.assert_called_once()
                call_args = mock_send.call_args[0][0]
                assert "https://pay.example.com/invoice" in call_args.text.body
                assert "[INSERT_URL_HERE]" not in call_args.text.body

    @pytest.mark.asyncio
    async def test_llm_failure_fallback_to_original_content(self) -> None:
        """Fall back to original content when LLM fails."""
        with patch(
            "api.routes.chat.chat_completions.call_llm_default",
            side_effect=Exception("LLM error"),
        ):
            with patch(
                "api.routes.chat.chat_completions.send_message",
                return_value={"status": "sent"},
            ) as mock_send:
                await _send_urls_via_sms(
                    collected_content=["Order: https://example.com/order"],
                    sender_identifier="+15551234567",
                    recipient_identifier="+15557654321",
                )

                # Verify SMS still sent with original content
                mock_send.assert_called_once()
                call_args = mock_send.call_args[0][0]
                assert "https://example.com/order" in call_args.text.body

    @pytest.mark.asyncio
    async def test_missing_placeholder_appends_url(self) -> None:
        """Append URL when placeholder not found in summary."""
        mock_response = SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content="Your order is ready"))
            ]
        )

        with patch(
            "api.routes.chat.chat_completions.call_llm_default",
            return_value=mock_response,
        ):
            with patch(
                "api.routes.chat.chat_completions.send_message",
                return_value={"status": "sent"},
            ) as mock_send:
                await _send_urls_via_sms(
                    collected_content=["Order: https://example.com/order"],
                    sender_identifier="+15551234567",
                    recipient_identifier="+15557654321",
                )

                mock_send.assert_called_once()
                call_args = mock_send.call_args[0][0]
                assert (
                    "Your order is ready\nhttps://example.com/order"
                    in call_args.text.body
                )

    @pytest.mark.asyncio
    async def test_invalid_identifiers_skip_sending(self) -> None:
        """Skip sending when sender or recipient identifiers invalid."""
        with patch("api.routes.chat.chat_completions.send_message") as mock_send:
            # Empty sender
            await _send_urls_via_sms(
                collected_content=["https://example.com"],
                sender_identifier="",
                recipient_identifier="+15557654321",
            )
            mock_send.assert_not_called()

            # None recipient
            await _send_urls_via_sms(
                collected_content=["https://example.com"],
                sender_identifier="+15551234567",
                recipient_identifier=None,  # type: ignore[arg-type]
            )
            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_persist_message_on_successful_send(self) -> None:
        """Persist message to conversation when SMS sent successfully and call_id provided."""
        mock_conversation = SimpleNamespace(id=uuid.uuid4())
        mock_conv_repo = AsyncMock()
        mock_conv_repo.get_conversation_by_call_id = AsyncMock(
            return_value=mock_conversation
        )

        mock_message_repo = AsyncMock()
        mock_message_repo.add_message_to_conversation = AsyncMock()

        mock_session = AsyncMock()

        mock_response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="Order link: [INSERT_URL_HERE]")
                )
            ]
        )

        # Mock AsyncSessionLocal to return our mock session
        mock_session_context = AsyncMock()
        mock_session_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_context.__aexit__ = AsyncMock(return_value=None)

        # Mock asyncio.to_thread to avoid actual threading in tests
        async def mock_to_thread(func, *args):
            return func(*args)

        with patch(
            "api.routes.chat.chat_completions.call_llm_default",
            return_value=mock_response,
        ):
            with patch(
                "api.routes.chat.chat_completions.send_message",
                return_value={"status": "scheduled"},
            ):
                with patch(
                    "api.routes.chat.chat_completions.asyncio.to_thread",
                    side_effect=mock_to_thread,
                ):
                    with patch(
                        "api.routes.chat.chat_completions.db.ConversationRepositoryAsync",
                        return_value=mock_conv_repo,
                    ):
                        with patch(
                            "api.routes.chat.chat_completions.db.MessageRepositoryAsync",
                            return_value=mock_message_repo,
                        ):
                            with patch(
                                "db.session.AsyncSessionLocal",
                                return_value=mock_session_context,
                            ):
                                await _send_urls_via_sms(
                                    collected_content=["https://example.com/order"],
                                    sender_identifier="+15551234567",
                                    recipient_identifier="+15557654321",
                                    call_id="call-123",
                                )

                                # Verify conversation looked up
                                mock_conv_repo.get_conversation_by_call_id.assert_called_once_with(
                                    "call-123"
                                )

                                # Verify message persisted
                                mock_message_repo.add_message_to_conversation.assert_called_once()

                                # Verify session was committed
                                mock_session.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Chat Completions Endpoint Tests
# ---------------------------------------------------------------------------


class TestChatCompletionsAgno:
    """Test chat_completions_agno() main function."""

    @pytest.mark.asyncio
    async def test_non_streaming_mode_raises_error(self) -> None:
        """Raise 400 error when streaming not enabled."""
        request = ChatCompletionRequest(
            model='{"sender_identifier": "user", "recipient_identifier": "agent"}',
            message="Hello",
            stream=False,
        )
        session = AsyncMock()
        request_context = RequestContext()

        with pytest.raises(HTTPException) as exc_info:
            await chat_completions_agno(
                request, request.model, request_context, session
            )

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "STREAMING_REQUIRED" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_invalid_model_json_raises_error(self) -> None:
        """Raise 500 error when model string is invalid JSON (caught by generic exception handler)."""
        request = ChatCompletionRequest(
            model="not valid json {",
            message="Hello",
            stream=True,
        )
        session = AsyncMock()
        request_context = RequestContext()

        with pytest.raises(HTTPException) as exc_info:
            await chat_completions_agno(
                request, request.model, request_context, session
            )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "INTERNAL_SERVER_ERROR" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_missing_message_and_messages_raises_error(self) -> None:
        """Raise 400 error when neither message nor messages provided."""
        request = ChatCompletionRequest(
            model='{"sender_identifier": "user", "recipient_identifier": "agent"}',
            message=None,
            messages=[],
            stream=True,
        )
        session = AsyncMock()
        request_context = RequestContext()

        with pytest.raises(HTTPException) as exc_info:
            await chat_completions_agno(
                request, request.model, request_context, session
            )

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.asyncio
    async def test_successful_streaming_response(self) -> None:
        """Return streaming response with proper headers."""
        request = ChatCompletionRequest(
            model='{"sender_identifier": "+15551234567", "recipient_identifier": "+15557654321"}',
            message="Hello",
            stream=True,
        )
        session = AsyncMock()
        request_context = RequestContext()

        # Mock get_chat_response_stream
        async def mock_stream():
            delta = SimpleNamespace(role="assistant", content="Hello")
            choice = SimpleNamespace(index=0, delta=delta, finish_reason=None)
            chunk = SimpleNamespace(
                id="chatcmpl-123",
                object="chat.completion.chunk",
                created=1234567890,
                model="gpt-4",
                choices=[choice],
            )
            chunk.model_dump = lambda: {
                "id": "chatcmpl-123",
                "object": "chat.completion.chunk",
                "created": 1234567890,
                "model": "gpt-4",
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": "Hello"},
                        "finish_reason": None,
                    }
                ],
            }
            yield chunk

        with patch(
            "api.routes.chat.chat_completions.get_chat_response_stream",
            return_value=mock_stream(),
        ):
            with patch("api.routes.chat.chat_completions._send_urls_via_sms"):
                response = await chat_completions_agno(
                    request, request.model, request_context, session
                )

        assert response.media_type == "text/event-stream"
        assert "Cache-Control" in response.headers
        assert response.headers["Cache-Control"] == "no-cache"
        assert response.headers["Connection"] == "keep-alive"
        assert response.headers["X-Accel-Buffering"] == "no"

    @pytest.mark.asyncio
    async def test_stream_generates_proper_sse_format(self) -> None:
        """Generate proper Server-Sent Events format."""
        request = ChatCompletionRequest(
            model='{"sender_identifier": "+15551234567", "recipient_identifier": "+15557654321"}',
            message="Hello",
            stream=True,
        )
        session = AsyncMock()
        request_context = RequestContext()

        async def mock_stream():
            delta = SimpleNamespace(content="Hello")
            choice = SimpleNamespace(index=0, delta=delta, finish_reason=None)
            chunk = SimpleNamespace(
                id="chatcmpl-123",
                object="chat.completion.chunk",
                created=1234567890,
                model="gpt-4",
                choices=[choice],
            )
            chunk.model_dump = lambda: {
                "id": "chatcmpl-123",
                "object": "chat.completion.chunk",
                "created": 1234567890,
                "model": "gpt-4",
                "choices": [
                    {"index": 0, "delta": {"content": "Hello"}, "finish_reason": None}
                ],
            }
            yield chunk

        with patch(
            "api.routes.chat.chat_completions.get_chat_response_stream",
            return_value=mock_stream(),
        ):
            with patch("api.routes.chat.chat_completions._send_urls_via_sms"):
                response = await chat_completions_agno(
                    request, request.model, request_context, session
                )

                # Consume the stream
                chunks = []
                async for chunk in response.body_iterator:
                    chunk_str = (
                        chunk.decode("utf-8")
                        if isinstance(chunk, bytes)
                        else str(chunk)
                    )
                    chunks.append(chunk_str)

                # Verify SSE format
                full_stream = "".join(chunks)
                assert "data: " in full_stream
                assert "[DONE]" in full_stream

    @pytest.mark.asyncio
    async def test_exception_during_streaming_returns_fallback(self) -> None:
        """Return fallback message when exception occurs during streaming."""
        request = ChatCompletionRequest(
            model='{"sender_identifier": "+15551234567", "recipient_identifier": "+15557654321"}',
            message="Hello",
            stream=True,
        )
        session = AsyncMock()
        request_context = RequestContext()

        async def mock_stream_with_error():
            raise Exception("Streaming error")
            # This yield is unreachable but needed for async generator syntax
            if False:
                yield

        with patch(
            "api.routes.chat.chat_completions.get_chat_response_stream",
            return_value=mock_stream_with_error(),
        ):
            response = await chat_completions_agno(
                request, request.model, request_context, session
            )

            # Consume the stream
            chunks = []
            async for chunk in response.body_iterator:
                decoded = (
                    chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)
                )
                chunks.append(decoded)

            # Verify fallback message present
            full_response = "".join(chunks)
            assert (
                "I apologize, but I'm unable to process your request" in full_response
            )

    @pytest.mark.asyncio
    async def test_cancelled_error_logs_and_stops_stream(self) -> None:
        """CancelledError is caught, logged, and stream stops gracefully."""
        request = ChatCompletionRequest(
            model='{"sender_identifier": "+15551234567", "recipient_identifier": "+15557654321"}',
            message="Hello",
            stream=True,
        )
        session = AsyncMock()
        request_context = RequestContext()

        async def mock_stream_cancelled():
            yield SimpleNamespace(
                id="chatcmpl-123",
                object="chat.completion.chunk",
                created=1234567890,
                model="gpt-4",
                choices=[
                    SimpleNamespace(
                        index=0, delta=SimpleNamespace(content="Hi"), finish_reason=None
                    )
                ],
                model_dump=lambda: {
                    "id": "chatcmpl-123",
                    "choices": [{"index": 0, "delta": {"content": "Hi"}}],
                },
            )
            raise asyncio.CancelledError()

        with patch(
            "api.routes.chat.chat_completions.get_chat_response_stream",
            return_value=mock_stream_cancelled(),
        ):
            response = await chat_completions_agno(
                request, request.model, request_context, session
            )

            # CancelledError is caught internally, stream should stop gracefully
            chunks_received = 0
            try:
                async for _ in response.body_iterator:
                    chunks_received += 1
            except asyncio.CancelledError:
                pass  # Expected to be raised

            # Should have received at least the first chunk before cancellation
            assert chunks_received >= 1


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------


class TestChatCompletionsIntegration:
    """Integration tests for full chat completions flow."""

    @pytest.mark.asyncio
    async def test_end_to_end_streaming_with_url_extraction(self) -> None:
        """Test complete flow: streaming response + URL extraction + SMS sending."""
        request = ChatCompletionRequest(
            model='{"sender_identifier": "+15551234567", "recipient_identifier": "+15557654321"}',
            message="What's the order status?",
            stream=True,
        )
        session = AsyncMock()
        request_context = RequestContext()

        # Mock streaming response with URL
        async def mock_stream():
            chunks_data = [
                "Your order is ready! ",
                "Pick it up at https://example.com/order/123",
            ]
            for content in chunks_data:
                delta = SimpleNamespace(content=content)
                choice = SimpleNamespace(index=0, delta=delta, finish_reason=None)
                chunk = SimpleNamespace(
                    id="chatcmpl-123",
                    object="chat.completion.chunk",
                    created=1234567890,
                    model="gpt-4",
                    choices=[choice],
                )
                chunk.model_dump = lambda c=content: {
                    "id": "chatcmpl-123",
                    "object": "chat.completion.chunk",
                    "created": 1234567890,
                    "model": "gpt-4",
                    "choices": [
                        {"index": 0, "delta": {"content": c}, "finish_reason": None}
                    ],
                }
                yield chunk

        mock_llm_response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="Your order is ready: [INSERT_URL_HERE]"
                    )
                )
            ]
        )

        # Mock asyncio.to_thread to avoid actual threading in tests
        async def mock_to_thread(func, *args):
            return func(*args)

        with patch(
            "api.routes.chat.chat_completions.get_chat_response_stream",
            return_value=mock_stream(),
        ):
            with patch(
                "api.routes.chat.chat_completions.call_llm_default",
                return_value=mock_llm_response,
            ):
                with patch(
                    "api.routes.chat.chat_completions.asyncio.to_thread",
                    side_effect=mock_to_thread,
                ):
                    with patch(
                        "api.routes.chat.chat_completions.send_message",
                        return_value={"status": "sent"},
                    ) as mock_send:
                        response = await chat_completions_agno(
                            request, request.model, request_context, session
                        )

                        # Consume the stream to trigger URL extraction
                        chunks = []
                        async for chunk in response.body_iterator:
                            chunks.append(chunk)

                        # No need to wait - SMS sending happens before [DONE] is sent

                        # Verify SMS was sent with URL
                        mock_send.assert_called_once()
                        sms_message = mock_send.call_args[0][0]
                        assert "https://example.com/order/123" in sms_message.text.body
