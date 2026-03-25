# pyright: reportGeneralTypeIssues=false, reportOptionalMemberAccess=false, reportAttributeAccessIssue=false, reportCallIssue=false
"""Tests for LiveKitTool — call transfer via metadata update."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from livekit import api as livekit_api

from agent.tool import ToolMetadata
from tools.livekit_tool._implementation import LiveKitTool

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_metadata(**overrides) -> ToolMetadata:
    defaults = {
        "agent_id": uuid.uuid4(),
        "account_id": uuid.uuid4(),
        "account_name": "Test Account",
        "user_id": uuid.uuid4(),
        "session_id": uuid.uuid4(),
        "project_id": uuid.uuid4(),
        "timezone": "America/New_York",
        "customer_phone": "+15551111111",
        "store_phone": "+15552222222",
        "channel": "voice",
    }
    defaults.update(overrides)
    return ToolMetadata(**defaults)


def _make_lk_api() -> MagicMock:
    """Create a mock LiveKitAPI with an async room service."""
    mock_api = MagicMock()
    mock_room = MagicMock()
    mock_room.update_room_metadata = AsyncMock(return_value=None)
    mock_api.room = mock_room
    return mock_api


def _make_tool(
    room_name: str | None = "call-room-1",
    transfer_destinations: dict[str, str] | None = None,
    metadata_overrides: dict | None = None,
    mock_lk_api: bool = True,
) -> LiveKitTool:
    """Create a LiveKitTool with sensible defaults for testing."""
    if transfer_destinations is None:
        transfer_destinations = {"general": "+15559876543"}
    meta = _make_metadata(**(metadata_overrides or {}))

    # Mock environment variables and LiveKitAPI constructor
    with patch.dict(
        "os.environ",
        {
            "LIVEKIT_URL": "https://test.livekit.cloud" if mock_lk_api else "",
            "LIVEKIT_API_KEY": "test-key" if mock_lk_api else "",
            "LIVEKIT_API_SECRET": "test-secret" if mock_lk_api else "",
        },
    ):
        if mock_lk_api:
            with patch(
                "tools.livekit_tool._implementation.livekit_api.LiveKitAPI"
            ) as mock_api_class:
                mock_api_class.return_value = _make_lk_api()
                tool = LiveKitTool(
                    tool_metadata=meta,
                    room_name=room_name,
                    transfer_destinations=transfer_destinations,
                )
                # Store reference to mock API for test assertions
                tool.lk_api = mock_api_class.return_value
                return tool
        else:
            tool = LiveKitTool(
                tool_metadata=meta,
                room_name=room_name,
                transfer_destinations=transfer_destinations,
            )
            return tool


# ---------------------------------------------------------------------------
# Integration tests: call_transfer — success paths
# ---------------------------------------------------------------------------


class TestCallTransferSuccess:
    @pytest.mark.asyncio
    async def test_basic_call_transfer(self) -> None:
        """Basic call transfer succeeds."""
        tool = _make_tool()
        result = await tool.call_transfer(purpose="general")

        assert result == "Call transfer has been initiated"
        tool.lk_api.room.update_room_metadata.assert_awaited_once()

        # Verify the request passed to LiveKit
        call_args = tool.lk_api.room.update_room_metadata.call_args
        request = call_args[0][0]
        assert isinstance(request, livekit_api.UpdateRoomMetadataRequest)
        assert request.room == "call-room-1"
        assert '"transfer_message":' in request.metadata
        assert '"transfer_to": "+15559876543"' in request.metadata

    @pytest.mark.asyncio
    async def test_transfer_with_complaint_purpose(self) -> None:
        """Call transfer with complaint purpose succeeds."""
        tool = _make_tool(
            transfer_destinations={
                "general": "+15559876543",
                "complaint": "+15550001111",
            }
        )
        result = await tool.call_transfer(purpose="complaint")

        assert result == "Call transfer has been initiated"
        request = tool.lk_api.room.update_room_metadata.call_args[0][0]
        assert '"transfer_message":' in request.metadata
        assert '"transfer_to": "+15550001111"' in request.metadata

    @pytest.mark.asyncio
    async def test_default_purpose_is_general(self) -> None:
        """Calling with no purpose argument defaults to 'general'."""
        tool = _make_tool()
        result = await tool.call_transfer()

        assert result == "Call transfer has been initiated"
        request = tool.lk_api.room.update_room_metadata.call_args[0][0]
        assert '"transfer_message":' in request.metadata
        assert '"transfer_to": "+15559876543"' in request.metadata

    @pytest.mark.asyncio
    async def test_purpose_fallback_to_general(self) -> None:
        """When requested purpose not found, falls back to general."""
        tool = _make_tool(transfer_destinations={"general": "+15559876543"})
        result = await tool.call_transfer(purpose="unknown_purpose")

        assert result == "Call transfer has been initiated"
        request = tool.lk_api.room.update_room_metadata.call_args[0][0]
        assert '"transfer_message":' in request.metadata
        assert '"transfer_to": "+15559876543"' in request.metadata

    @pytest.mark.asyncio
    async def test_purpose_normalization(self) -> None:
        """Purpose is normalized: stripped, lowercased."""
        tool = _make_tool(
            transfer_destinations={
                "general": "+15559876543",
                "complaint": "+15550001111",
            }
        )
        result = await tool.call_transfer(purpose="  COMPLAINT  ")

        assert result == "Call transfer has been initiated"
        request = tool.lk_api.room.update_room_metadata.call_args[0][0]
        assert '"transfer_message":' in request.metadata
        assert '"transfer_to": "+15550001111"' in request.metadata

    @pytest.mark.asyncio
    async def test_empty_purpose_defaults_to_general(self) -> None:
        """Empty or whitespace-only purpose defaults to 'general'."""
        tool = _make_tool(transfer_destinations={"general": "+15559876543"})
        result = await tool.call_transfer(purpose="   ")

        assert result == "Call transfer has been initiated"
        request = tool.lk_api.room.update_room_metadata.call_args[0][0]
        assert '"transfer_message":' in request.metadata
        assert '"transfer_to": "+15559876543"' in request.metadata


# ---------------------------------------------------------------------------
# Integration tests: call_transfer — validation errors
# ---------------------------------------------------------------------------


class TestCallTransferValidation:
    @pytest.mark.asyncio
    async def test_non_voice_channel_rejected(self) -> None:
        """Non-voice channel returns error."""
        tool = _make_tool(metadata_overrides={"channel": "sms"})
        result = await tool.call_transfer()

        assert "only available for voice calls" in result
        tool.lk_api.room.update_room_metadata.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_web_channel_rejected(self) -> None:
        """Web channel returns error."""
        tool = _make_tool(metadata_overrides={"channel": "web"})
        result = await tool.call_transfer()

        assert "only available for voice calls" in result
        tool.lk_api.room.update_room_metadata.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_none_channel_allows_transfer(self) -> None:
        """None channel (unset) does not block transfer."""
        tool = _make_tool(metadata_overrides={"channel": None})
        result = await tool.call_transfer()

        assert result == "Call transfer has been initiated"

    @pytest.mark.asyncio
    async def test_voice_channel_allows_transfer(self) -> None:
        """Explicit voice channel allows transfer."""
        tool = _make_tool(metadata_overrides={"channel": "voice"})
        result = await tool.call_transfer()

        assert result == "Call transfer has been initiated"

    @pytest.mark.asyncio
    async def test_missing_lk_api(self) -> None:
        """Missing LiveKit API client returns error."""
        tool = _make_tool(mock_lk_api=False)
        result = await tool.call_transfer()

        assert "LiveKit API client is not available" in result

    @pytest.mark.asyncio
    async def test_missing_room_name(self) -> None:
        """Missing room name returns error."""
        tool = _make_tool(room_name=None)
        result = await tool.call_transfer()

        assert "room info is not available" in result
        tool.lk_api.room.update_room_metadata.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_destination_configured(self) -> None:
        """No destination for purpose and no general fallback returns error."""
        tool = _make_tool(transfer_destinations={})
        result = await tool.call_transfer(purpose="complaint")

        assert "No transfer destination configured" in result
        tool.lk_api.room.update_room_metadata.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_general_fallback(self) -> None:
        """No general fallback when purpose not found returns error."""
        tool = _make_tool(transfer_destinations={"faq": "+15550001111"})
        result = await tool.call_transfer(purpose="complaint")

        assert "No transfer destination configured" in result
        tool.lk_api.room.update_room_metadata.assert_not_awaited()


# ---------------------------------------------------------------------------
# Integration tests: constructor
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Integration tests: call_transfer — LiveKit API errors
# ---------------------------------------------------------------------------


class TestCallTransferErrors:
    @pytest.mark.asyncio
    async def test_room_not_found_returns_call_ended(self) -> None:
        """TwirpError NOT_FOUND → graceful 'call has already ended' message."""
        tool = _make_tool()
        # Override the mock to raise NOT_FOUND error
        tool.lk_api.room.update_room_metadata = AsyncMock(
            side_effect=livekit_api.TwirpError(
                code=livekit_api.TwirpErrorCode.NOT_FOUND,
                msg="room not found",
                status=404,
            )
        )
        result = await tool.call_transfer()

        assert result == "Call has already ended. Transfer is no longer possible."

    @pytest.mark.asyncio
    async def test_twirp_internal_error(self) -> None:
        """TwirpError INTERNAL → generic error message returned."""
        tool = _make_tool()
        # Override the mock to raise INTERNAL error
        tool.lk_api.room.update_room_metadata = AsyncMock(
            side_effect=livekit_api.TwirpError(
                code=livekit_api.TwirpErrorCode.INTERNAL,
                msg="internal server error",
                status=500,
            )
        )
        result = await tool.call_transfer()

        # Should return generic message, not leak backend details
        assert result == "Failed to update LiveKit metadata. Please try again."
        assert "internal server error" not in result

    @pytest.mark.asyncio
    async def test_unexpected_exception(self) -> None:
        """Unexpected exception → generic error message returned."""
        tool = _make_tool()
        # Override the mock to raise unexpected exception
        tool.lk_api.room.update_room_metadata = AsyncMock(
            side_effect=RuntimeError("connection reset")
        )
        result = await tool.call_transfer()

        # Should return generic message, not leak backend details
        assert result == "An unexpected error occurred. Please try again."
        assert "connection reset" not in result


# ---------------------------------------------------------------------------
# Integration tests: constructor
# ---------------------------------------------------------------------------


class TestConstructor:
    def test_tool_name_is_livekit_tool(self) -> None:
        tool = _make_tool()
        assert tool.name == "livekit_tool"

    def test_ignores_unknown_kwargs(self) -> None:
        """Unknown kwargs from raw_config are accepted and ignored."""
        meta = _make_metadata()
        with patch.dict("os.environ", {}):
            tool = LiveKitTool(
                tool_metadata=meta,
                room_name="room-1",
                transfer_destinations={"general": "+15559876543"},
                some_unknown_arg="should not raise",
                another_arg=42,
            )
        assert tool.name == "livekit_tool"

    def test_no_destinations_gives_empty_dict(self) -> None:
        """No transfer_destinations → empty dict."""
        meta = _make_metadata()
        with patch.dict("os.environ", {}):
            tool = LiveKitTool(
                tool_metadata=meta,
                room_name="room-1",
            )
        assert tool.transfer_destinations == {}

    def test_livekit_api_created_from_env_vars(self) -> None:
        """LiveKitAPI is created when environment variables are set."""
        meta = _make_metadata()
        with patch.dict(
            "os.environ",
            {
                "LIVEKIT_URL": "https://test.livekit.cloud",
                "LIVEKIT_API_KEY": "test-key",
                "LIVEKIT_API_SECRET": "test-secret",
            },
        ):
            with patch(
                "tools.livekit_tool._implementation.livekit_api.LiveKitAPI"
            ) as mock_api_class:
                tool = LiveKitTool(
                    tool_metadata=meta,
                    room_name="room-1",
                )
                mock_api_class.assert_called_once_with(
                    url="https://test.livekit.cloud",
                    api_key="test-key",
                    api_secret="test-secret",
                )
                assert tool.lk_api is not None

    def test_livekit_api_not_created_without_env_vars(self) -> None:
        """LiveKitAPI is not created when environment variables are missing."""
        meta = _make_metadata()
        with patch.dict("os.environ", {}, clear=True):
            tool = LiveKitTool(
                tool_metadata=meta,
                room_name="room-1",
            )
            assert not hasattr(tool, "lk_api") or tool.lk_api is None
