# pyright: reportGeneralTypeIssues=false, reportAttributeAccessIssue=false
"""Tests for LiveKit auto-swap (Gap 1) and context injection (Gap 2).

Gap 1: When room_name + participant_identity are present, vapi_tool is
auto-swapped to livekit_transfer_tool in _get_agent_tools().

Gap 2: room_name, participant_identity, and lk_api are injected into
livekit_transfer_tool args so LiveKitTransferTool.call_transfer() can
execute SIP REFER.
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
    """Stub _populate_vapi_tool_args to avoid DB calls."""
    updated = tool_args.copy()
    updated.pop("transfer_destinations", None)
    updated["transfer_destinations"] = {}
    updated["transfer_message"] = "Transferring you now."
    return updated


def _get_tools(rc):
    """Patch helpers and call _get_agent_tools."""
    return (
        patch.object(rc, "_populate_vapi_tool_args", side_effect=_mock_populate),
        patch.object(rc, "_get_project_tools_override", return_value={}),
        patch.object(rc, "_get_project_integration_tools", return_value=[]),
    )


# ---------------------------------------------------------------------------
# Gap 1: Auto-swap tests
# ---------------------------------------------------------------------------


class TestLiveKitAutoSwap:
    """vapi_tool is auto-swapped to livekit_transfer_tool when LiveKit context is present."""

    @pytest.mark.asyncio
    async def test_vapi_tool_swapped_to_livekit_when_livekit_context_present(
        self,
    ) -> None:
        """room_name + participant_identity set, agent has vapi_tool -> livekit_transfer_tool."""
        rc = _make_raw_config(
            "vapi_tool",
            room_name="room-abc",
            participant_identity="participant-xyz",
        )
        p1, p2, p3 = _get_tools(rc)
        with p1, p2, p3:
            tool_config = await rc._get_agent_tools(session=None)

        tool_names = [t.tool_name for t in tool_config.identifiers]
        assert "livekit_transfer_tool" in tool_names
        assert "vapi_tool" not in tool_names

    @pytest.mark.asyncio
    async def test_vapi_tool_stays_when_no_livekit_context(self) -> None:
        """No room_name/participant_identity -> vapi_tool remains unchanged."""
        rc = _make_raw_config("vapi_tool")
        p1, p2, p3 = _get_tools(rc)
        with p1, p2, p3:
            tool_config = await rc._get_agent_tools(session=None)

        tool_names = [t.tool_name for t in tool_config.identifiers]
        assert "vapi_tool" in tool_names
        assert "livekit_transfer_tool" not in tool_names

    @pytest.mark.asyncio
    async def test_no_swap_when_livekit_tool_already_present(self) -> None:
        """Agent config already has livekit_transfer_tool + LiveKit context -> no duplicate."""
        rc = _make_raw_config(
            "livekit_transfer_tool",
            room_name="room-abc",
            participant_identity="participant-xyz",
        )
        p1, p2, p3 = _get_tools(rc)
        with p1, p2, p3:
            tool_config = await rc._get_agent_tools(session=None)

        tool_names = [t.tool_name for t in tool_config.identifiers]
        assert tool_names.count("livekit_transfer_tool") == 1

    @pytest.mark.asyncio
    async def test_no_swap_when_only_room_name_present(self) -> None:
        """Only room_name set (no participant_identity) -> no swap."""
        rc = _make_raw_config(
            "vapi_tool",
            room_name="room-abc",
        )
        p1, p2, p3 = _get_tools(rc)
        with p1, p2, p3:
            tool_config = await rc._get_agent_tools(session=None)

        tool_names = [t.tool_name for t in tool_config.identifiers]
        assert "vapi_tool" in tool_names
        assert "livekit_transfer_tool" not in tool_names

    @pytest.mark.asyncio
    async def test_no_swap_when_only_participant_identity_present(self) -> None:
        """Only participant_identity set (no room_name) -> no swap."""
        rc = _make_raw_config(
            "vapi_tool",
            participant_identity="participant-xyz",
        )
        p1, p2, p3 = _get_tools(rc)
        with p1, p2, p3:
            tool_config = await rc._get_agent_tools(session=None)

        tool_names = [t.tool_name for t in tool_config.identifiers]
        assert "vapi_tool" in tool_names
        assert "livekit_transfer_tool" not in tool_names

    @pytest.mark.asyncio
    async def test_swap_preserves_tool_order(self) -> None:
        """Agent has [other_tool, vapi_tool, another_tool] -> after swap, order preserved."""
        rc = _make_raw_config(
            "some_other_tool",
            room_name="room-abc",
            participant_identity="participant-xyz",
            extra_tools=[
                {"tool_name": "vapi_tool", "tool_args": {}, "access_metadata": False},
                {
                    "tool_name": "another_tool",
                    "tool_args": {},
                    "access_metadata": False,
                },
            ],
        )
        p1, p2, p3 = _get_tools(rc)
        with p1, p2, p3:
            tool_config = await rc._get_agent_tools(session=None)

        tool_names = [t.tool_name for t in tool_config.identifiers]
        assert tool_names == [
            "some_other_tool",
            "livekit_transfer_tool",
            "another_tool",
        ]

    @pytest.mark.asyncio
    async def test_swap_preserves_tool_args(self) -> None:
        """vapi_tool had access_metadata=True and custom args -> swapped tool inherits them."""
        rc = _make_raw_config(
            "vapi_tool",
            tool_args={"custom_key": "custom_value"},
            room_name="room-abc",
            participant_identity="participant-xyz",
        )
        p1, p2, p3 = _get_tools(rc)
        with p1, p2, p3:
            tool_config = await rc._get_agent_tools(session=None)

        tool = tool_config.identifiers[0]
        assert tool.tool_name == "livekit_transfer_tool"
        assert tool.access_metadata is True


# ---------------------------------------------------------------------------
# Gap 2: Context injection tests
# ---------------------------------------------------------------------------


class TestLiveKitContextInjection:
    """room_name, participant_identity, and lk_api injected into livekit_transfer_tool args."""

    @pytest.mark.asyncio
    async def test_room_name_and_participant_identity_injected(self) -> None:
        """LiveKit context present -> tool_args contain room_name and participant_identity."""
        rc = _make_raw_config(
            "vapi_tool",
            room_name="room-abc",
            participant_identity="participant-xyz",
        )
        p1, p2, p3 = _get_tools(rc)
        with p1, p2, p3:
            tool_config = await rc._get_agent_tools(session=None)

        tool = tool_config.identifiers[0]
        assert tool.tool_name == "livekit_transfer_tool"
        assert tool.args["room_name"] == "room-abc"
        assert tool.args["participant_identity"] == "participant-xyz"

    @pytest.mark.asyncio
    async def test_lk_api_injected_when_env_vars_set(self) -> None:
        """LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET set -> lk_api present."""
        rc = _make_raw_config(
            "vapi_tool",
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
            "vapi_tool",
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
        rc = _make_raw_config("vapi_tool")
        p1, p2, p3 = _get_tools(rc)
        with p1, p2, p3:
            tool_config = await rc._get_agent_tools(session=None)

        tool = tool_config.identifiers[0]
        assert tool.tool_name == "vapi_tool"
        assert "room_name" not in tool.args
        assert "participant_identity" not in tool.args
        assert "lk_api" not in tool.args

    @pytest.mark.asyncio
    async def test_injection_works_with_explicit_destinations(self) -> None:
        """LiveKit context + explicit SIP destinations -> both merge AND injection happen."""
        explicit_destinations = {"catering": "sip:catering@sip.provider.com"}
        rc = _make_raw_config(
            "vapi_tool",
            tool_args={"transfer_destinations": explicit_destinations},
            room_name="room-abc",
            participant_identity="participant-xyz",
        )

        contact_destinations = {"general": "+15559876543"}

        async def mock_populate_with_contacts(tool_args, session=None):
            updated = tool_args.copy()
            updated.pop("transfer_destinations", None)
            updated["transfer_destinations"] = contact_destinations.copy()
            updated["transfer_message"] = "Transferring you now."
            return updated

        with patch.object(
            rc, "_populate_vapi_tool_args", side_effect=mock_populate_with_contacts
        ):
            with patch.object(rc, "_get_project_tools_override", return_value={}):
                with patch.object(
                    rc, "_get_project_integration_tools", return_value=[]
                ):
                    with patch.dict(
                        os.environ,
                        {
                            "LIVEKIT_URL": "",
                            "LIVEKIT_API_KEY": "",
                            "LIVEKIT_API_SECRET": "",
                        },
                    ):
                        tool_config = await rc._get_agent_tools(session=None)

        tool = tool_config.identifiers[0]
        assert tool.tool_name == "livekit_transfer_tool"
        # Context injection
        assert tool.args["room_name"] == "room-abc"
        assert tool.args["participant_identity"] == "participant-xyz"
        # Destination merge: explicit SIP overrides contact for same role,
        # contact-derived "general" preserved
        destinations = tool.args["transfer_destinations"]
        assert destinations["catering"] == "sip:catering@sip.provider.com"
        assert destinations["general"] == "+15559876543"


# ---------------------------------------------------------------------------
# No-regression tests
# ---------------------------------------------------------------------------


class TestNoRegressionVapi:
    """Existing Vapi behavior is preserved when no LiveKit context is present."""

    @pytest.mark.asyncio
    async def test_vapi_call_no_room_name_stays_vapi(self) -> None:
        """Standard Vapi call (no LiveKit fields) -> vapi_tool untouched."""
        rc = _make_raw_config("vapi_tool")
        p1, p2, p3 = _get_tools(rc)
        with p1, p2, p3:
            tool_config = await rc._get_agent_tools(session=None)

        tool = tool_config.identifiers[0]
        assert tool.tool_name == "vapi_tool"
        assert "room_name" not in tool.args
        assert "participant_identity" not in tool.args

    @pytest.mark.asyncio
    async def test_vapi_filtered_on_non_voice_channel(self) -> None:
        """Non-voice channel -> vapi_tool filtered out (existing behavior preserved)."""
        rc = _make_raw_config("vapi_tool", channel=Channel.SMS)
        p1, p2, p3 = _get_tools(rc)
        with p1, p2, p3:
            tool_config = await rc._get_agent_tools(session=None)

        assert len(tool_config.identifiers) == 0
