# pyright: reportGeneralTypeIssues=false, reportAttributeAccessIssue=false
"""Tests for auto-injection of livekit_tool on voice channels.

When no livekit tool is in the merged tool list but the channel is VOICE
and the project has transfer contacts configured, _get_agent_tools()
should auto-inject livekit_tool.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from db.tables.types import Channel
from services.agent_service._raw_config import RawConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_raw_config(
    agent_tools: list[dict] | None = None,
    channel: Channel = Channel.VOICE,
    room_name: str | None = "test-room",
    participant_identity: str | None = "test-participant",
    transfer_phone_number: str | None = "+15559999999",
) -> RawConfig:
    """Build a RawConfig with optional tools."""
    agent = MagicMock()
    agent.id = uuid.uuid4()
    agent.raw_config = {
        "tools": {"identifiers": agent_tools or []},
    }
    agent.memory_enabled = False
    agent.filler_words = {}

    project = MagicMock()
    project.id = uuid.uuid4()
    project.timezone = "America/New_York"
    project.raw_config = {}
    project.transfer_message = "Transferring you now."
    project.transfer_phone_number = transfer_phone_number

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


async def _mock_populate(tool_args: dict, session: object = None) -> dict:
    """Stub _populate_transfer_tool_args to avoid DB calls."""
    updated = tool_args.copy()
    updated.pop("transfer_destinations", None)
    updated["transfer_destinations"] = {"general": "+15559999999"}
    updated["transfer_message"] = "Transferring you now."
    return updated


def _mock_contact_repo(has_contacts: bool = True):
    """Return a mock ProjectContactRepositoryAsync class."""
    mock_repo_instance = MagicMock()
    if has_contacts:
        mock_repo_instance.list_contacts_by_project = AsyncMock(
            return_value=[uuid.uuid4()]
        )
    else:
        mock_repo_instance.list_contacts_by_project = AsyncMock(return_value=[])
    mock_repo_class = MagicMock(return_value=mock_repo_instance)
    return mock_repo_class


def _patch_helpers(rc: RawConfig, has_contacts: bool = True):
    """Return context managers that patch DB-dependent helpers."""
    return (
        patch.object(rc, "_populate_transfer_tool_args", side_effect=_mock_populate),
        patch.object(rc, "_get_project_tools_override", return_value={}),
        patch.object(rc, "_get_project_integration_tools", return_value=[]),
        patch(
            "services.agent_service._raw_config.ProjectContactRepositoryAsync",
            _mock_contact_repo(has_contacts),
        ),
    )


# ---------------------------------------------------------------------------
# Auto-injection tests
# ---------------------------------------------------------------------------

_MOCK_SESSION = MagicMock()


class TestAutoInjectLiveKitTool:
    """Auto-inject livekit_tool for voice channels when not explicitly configured."""

    @pytest.mark.asyncio
    async def test_injects_livekit_tool_for_voice(self) -> None:
        """Voice channel with contacts gets livekit_tool auto-injected."""
        rc = _make_raw_config()
        p1, p2, p3, p4 = _patch_helpers(rc)
        with p1, p2, p3, p4:
            tool_config = await rc._get_agent_tools(session=_MOCK_SESSION)

        tool_names = [t.tool_name for t in tool_config.identifiers]
        assert "livekit_tool" in tool_names

    @pytest.mark.asyncio
    async def test_no_injection_for_non_voice_channel(self) -> None:
        """Non-voice channels should not get livekit_tool injected."""
        rc = _make_raw_config(channel=Channel.SMS)
        p1, p2, p3, p4 = _patch_helpers(rc)
        with p1, p2, p3, p4:
            tool_config = await rc._get_agent_tools(session=_MOCK_SESSION)

        tool_names = [t.tool_name for t in tool_config.identifiers]
        assert "livekit_tool" not in tool_names

    @pytest.mark.asyncio
    async def test_no_injection_when_no_contacts_or_phone(self) -> None:
        """No contacts and no transfer_phone_number -> no injection."""
        rc = _make_raw_config(transfer_phone_number=None)
        p1, p2, p3, p4 = _patch_helpers(rc, has_contacts=False)
        with p1, p2, p3, p4:
            tool_config = await rc._get_agent_tools(session=_MOCK_SESSION)

        tool_names = [t.tool_name for t in tool_config.identifiers]
        assert "livekit_tool" not in tool_names

    @pytest.mark.asyncio
    async def test_no_injection_when_no_contacts_but_has_phone(self) -> None:
        """No contacts -> no injection, even if transfer_phone_number exists."""
        rc = _make_raw_config(transfer_phone_number="+15551234567")
        p1, p2, p3, p4 = _patch_helpers(rc, has_contacts=False)
        with p1, p2, p3, p4:
            tool_config = await rc._get_agent_tools(session=_MOCK_SESSION)

        tool_names = [t.tool_name for t in tool_config.identifiers]
        assert "livekit_tool" not in tool_names

    @pytest.mark.asyncio
    async def test_no_injection_when_livekit_tool_configured(self) -> None:
        """If livekit_tool is already in raw_config, don't add a second one."""
        existing_tools = [
            {
                "tool_name": "livekit_tool",
                "tool_args": {},
                "access_metadata": True,
            }
        ]
        rc = _make_raw_config(agent_tools=existing_tools)
        p1, p2, p3, p4 = _patch_helpers(rc)
        with p1, p2, p3, p4:
            tool_config = await rc._get_agent_tools(session=_MOCK_SESSION)

        livekit_tools = [
            t for t in tool_config.identifiers if t.tool_name == "livekit_tool"
        ]
        assert len(livekit_tools) == 1

    @pytest.mark.asyncio
    async def test_injected_tool_gets_populated(self) -> None:
        """Auto-injected tool should still get transfer_destinations populated."""
        rc = _make_raw_config()
        p1, p2, p3, p4 = _patch_helpers(rc)
        with p1, p2, p3, p4:
            tool_config = await rc._get_agent_tools(session=_MOCK_SESSION)

        tool = next(t for t in tool_config.identifiers if t.tool_name == "livekit_tool")
        assert tool.args.get("transfer_destinations") == {"general": "+15559999999"}
        assert tool.args.get("transfer_message") == "Transferring you now."
