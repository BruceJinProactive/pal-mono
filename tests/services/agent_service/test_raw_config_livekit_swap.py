# pyright: reportGeneralTypeIssues=false, reportAttributeAccessIssue=false
"""Tests for LiveKit transfer tool context injection.

When livekit_tool is configured on an agent, room_name,
participant_identity, and lk_api are injected into its args so
LiveKitTool.call_transfer() can execute SIP REFER.
"""

import os
import uuid
from unittest.mock import MagicMock, patch

import pytest

from db.tables.types import Channel
from services.agent_service._raw_config import RawConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_raw_config(
    tool_name: str,
    tool_args: dict | None = None,
    channel: Channel = Channel.VOICE,
    room_name: str | None = None,
    participant_identity: str | None = None,
    extra_tools: list[dict] | None = None,
) -> RawConfig:
    """Build a RawConfig with one or more tools configured in agent.raw_config."""
    identifiers = [
        {
            "tool_name": tool_name,
            "tool_args": tool_args or {},
            "access_metadata": True,
        }
    ]
    if extra_tools:
        identifiers.extend(extra_tools)

    agent = MagicMock()
    agent.id = uuid.uuid4()
    agent.raw_config = {"tools": {"identifiers": identifiers}}
    agent.memory_enabled = False
    agent.filler_words = {}

    project = MagicMock()
    project.id = uuid.uuid4()
    project.timezone = "America/New_York"
    project.raw_config = {}
    project.transfer_message = "Transferring you now."

    account = MagicMock()
    account.id = uuid.uuid4()
    account.name = "Test Account"

    return RawConfig(
        agent=agent,
        project=project,
        account=account,
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        channel=channel,
        sender_identifier="+15551111111",
        receiver_identifier="+15552222222",
        room_name=room_name,
        participant_identity=participant_identity,
    )


async def _mock_populate(tool_args, session=None):
    """Stub _populate_transfer_tool_args to avoid DB calls."""
    updated = tool_args.copy()
    updated.pop("transfer_destinations", None)
    updated["transfer_destinations"] = {}
    updated["transfer_message"] = "Transferring you now."
    return updated


def _get_tools(rc):
    """Patch helpers and call _get_agent_tools."""
    return (
        patch.object(rc, "_populate_transfer_tool_args", side_effect=_mock_populate),
        patch.object(rc, "_get_project_tools_override", return_value={}),
        patch.object(rc, "_get_project_integration_tools", return_value=[]),
    )


# ---------------------------------------------------------------------------
# Context injection tests
# ---------------------------------------------------------------------------


class TestLiveKitContextInjection:
    """room_name, participant_identity, and lk_api injected into livekit_tool args."""

    @pytest.mark.asyncio
    async def test_room_name_and_participant_identity_injected(self) -> None:
        """LiveKit context present -> tool_args contain room_name and participant_identity."""
        rc = _make_raw_config(
            "livekit_tool",
            room_name="room-abc",
            participant_identity="participant-xyz",
        )
        p1, p2, p3 = _get_tools(rc)
        with p1, p2, p3:
            tool_config = await rc._get_agent_tools(session=None)

        tool = tool_config.identifiers[0]
        assert tool.tool_name == "livekit_tool"
        assert tool.args["room_name"] == "room-abc"
        assert tool.args["participant_identity"] == "participant-xyz"

    @pytest.mark.asyncio
    async def test_lk_api_injected_when_env_vars_set(self) -> None:
        """LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET set -> lk_api present."""
        rc = _make_raw_config(
            "livekit_tool",
            room_name="room-abc",
            participant_identity="participant-xyz",
        )
        p1, p2, p3 = _get_tools(rc)
        with p1, p2, p3:
            with patch.dict(
                os.environ,
                {
                    "LIVEKIT_URL": "wss://test.livekit.cloud",
                    "LIVEKIT_API_KEY": "test-key",
                    "LIVEKIT_API_SECRET": "test-secret",
                },
            ):
                with patch(
                    "services.agent_service._raw_config.livekit_api.LiveKitAPI"
                ) as mock_lk_cls:
                    mock_lk_cls.return_value = MagicMock()
                    tool_config = await rc._get_agent_tools(session=None)

        tool = tool_config.identifiers[0]
        assert "lk_api" in tool.args
        mock_lk_cls.assert_called_once_with(
            url="wss://test.livekit.cloud",
            api_key="test-key",
            api_secret="test-secret",
        )

    @pytest.mark.asyncio
    async def test_lk_api_not_injected_when_env_vars_missing(self) -> None:
        """Env vars not set -> lk_api NOT in tool_args (room_name/participant_identity still are)."""
        rc = _make_raw_config(
            "livekit_tool",
            room_name="room-abc",
            participant_identity="participant-xyz",
        )
        p1, p2, p3 = _get_tools(rc)
        with p1, p2, p3:
            with patch.dict(
                os.environ,
                {"LIVEKIT_URL": "", "LIVEKIT_API_KEY": "", "LIVEKIT_API_SECRET": ""},
            ):
                tool_config = await rc._get_agent_tools(session=None)

        tool = tool_config.identifiers[0]
        assert tool.args["room_name"] == "room-abc"
        assert tool.args["participant_identity"] == "participant-xyz"
        assert "lk_api" not in tool.args

    @pytest.mark.asyncio
    async def test_no_injection_without_livekit_context(self) -> None:
        """No room_name/participant_identity -> tool_args have no LiveKit fields."""
        rc = _make_raw_config("livekit_tool")
        p1, p2, p3 = _get_tools(rc)
        with p1, p2, p3:
            tool_config = await rc._get_agent_tools(session=None)

        tool = tool_config.identifiers[0]
        assert tool.tool_name == "livekit_tool"
        assert "room_name" not in tool.args
        assert "participant_identity" not in tool.args
        assert "lk_api" not in tool.args
