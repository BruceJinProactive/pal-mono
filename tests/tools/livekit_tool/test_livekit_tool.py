# pyright: reportGeneralTypeIssues=false, reportOptionalMemberAccess=false, reportAttributeAccessIssue=false, reportCallIssue=false
"""Tests for LiveKitTool — call transfer via metadata update."""

import uuid

import pytest

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


def _make_tool(metadata_overrides: dict | None = None) -> LiveKitTool:
    """Create a LiveKitTool with sensible defaults for testing."""
    meta = _make_metadata(**(metadata_overrides or {}))
    return LiveKitTool(tool_metadata=meta)


# ---------------------------------------------------------------------------
# Integration tests: call_transfer — success paths
# ---------------------------------------------------------------------------


class TestCallTransferSuccess:
    @pytest.mark.asyncio
    async def test_basic_call_transfer(self) -> None:
        """Basic call transfer succeeds."""
        tool = _make_tool()
        result = await tool.call_transfer(purpose="general")

        assert "Call transfer requested" in result
        assert "general" in result

    @pytest.mark.asyncio
    async def test_transfer_with_complaint_purpose(self) -> None:
        """Call transfer with complaint purpose succeeds."""
        tool = _make_tool()
        result = await tool.call_transfer(purpose="complaint")

        assert "Call transfer requested" in result
        assert "complaint" in result

    @pytest.mark.asyncio
    async def test_default_purpose_is_general(self) -> None:
        """Calling with no purpose argument defaults to 'general'."""
        tool = _make_tool()
        result = await tool.call_transfer()

        assert "Call transfer requested" in result
        assert "general" in result


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

    @pytest.mark.asyncio
    async def test_web_channel_rejected(self) -> None:
        """Web channel returns error."""
        tool = _make_tool(metadata_overrides={"channel": "web"})
        result = await tool.call_transfer()

        assert "only available for voice calls" in result

    @pytest.mark.asyncio
    async def test_none_channel_allows_transfer(self) -> None:
        """None channel (unset) does not block transfer."""
        tool = _make_tool(metadata_overrides={"channel": None})
        result = await tool.call_transfer()

        assert "Call transfer requested" in result

    @pytest.mark.asyncio
    async def test_voice_channel_allows_transfer(self) -> None:
        """Explicit voice channel allows transfer."""
        tool = _make_tool(metadata_overrides={"channel": "voice"})
        result = await tool.call_transfer()

        assert "Call transfer requested" in result


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
        tool = LiveKitTool(
            tool_metadata=meta,
            some_unknown_arg="should not raise",
            another_arg=42,
        )
        assert tool.name == "livekit_tool"
