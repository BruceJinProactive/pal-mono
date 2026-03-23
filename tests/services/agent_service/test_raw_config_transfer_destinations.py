# pyright: reportGeneralTypeIssues=false, reportAttributeAccessIssue=false
"""Tests for transfer destination population in _raw_config._get_agent_tools.

Verifies that livekit_tool transfer_destinations are populated from
contacts via _populate_transfer_tool_args.
"""

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
) -> RawConfig:
    """Build a RawConfig with a single tool configured in agent.raw_config."""
    agent = MagicMock()
    agent.id = uuid.uuid4()
    agent.raw_config = {
        "tools": {
            "identifiers": [
                {
                    "tool_name": tool_name,
                    "tool_args": tool_args or {},
                    "access_metadata": True,
                }
            ]
        }
    }
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
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLiveKitTransferDestinations:
    """Transfer destinations are populated from contacts for livekit_tool."""

    @pytest.mark.asyncio
    async def test_contact_destinations_populated(self) -> None:
        """Contact-derived destinations are set by _populate_transfer_tool_args."""
        rc = _make_raw_config(
            "livekit_tool",
            tool_args={},
        )

        contact_destinations = {
            "general": "+15559876543",
            "complaint": "+15550001111",
        }

        async def mock_populate(tool_args, session=None):
            updated = tool_args.copy()
            updated["transfer_destinations"] = contact_destinations.copy()
            updated["transfer_message"] = "Transferring you now."
            return updated

        with patch.object(
            rc, "_populate_transfer_tool_args", side_effect=mock_populate
        ):
            with patch.object(rc, "_get_project_tools_override", return_value={}):
                with patch.object(
                    rc, "_get_project_integration_tools", return_value=[]
                ):
                    tool_config = await rc._get_agent_tools(session=None)

        tool = tool_config.identifiers[0]
        assert tool.tool_name == "livekit_tool"
        destinations = tool.args["transfer_destinations"]

        assert destinations["complaint"] == "+15550001111"
        assert destinations["general"] == "+15559876543"

    @pytest.mark.asyncio
    async def test_no_explicit_destinations_uses_contacts_only(self) -> None:
        """When no explicit destinations in raw_config, contacts table drives all."""
        rc = _make_raw_config(
            "livekit_tool",
            tool_args={},
        )

        contact_destinations = {"general": "+15559876543", "faq": "+15550002222"}

        async def mock_populate(tool_args, session=None):
            updated = tool_args.copy()
            updated.pop("transfer_destinations", None)
            updated["transfer_destinations"] = contact_destinations.copy()
            return updated

        with patch.object(
            rc, "_populate_transfer_tool_args", side_effect=mock_populate
        ):
            with patch.object(rc, "_get_project_tools_override", return_value={}):
                with patch.object(
                    rc, "_get_project_integration_tools", return_value=[]
                ):
                    tool_config = await rc._get_agent_tools(session=None)

        destinations = tool_config.identifiers[0].args["transfer_destinations"]
        assert destinations == {"general": "+15559876543", "faq": "+15550002222"}

    @pytest.mark.asyncio
    async def test_stale_raw_config_destinations_cleared(self) -> None:
        """Stale transfer_destinations from raw_config are cleared when no contacts exist."""
        rc = _make_raw_config(
            "livekit_tool",
            tool_args={"transfer_destinations": {"stale_role": "+15550009999"}},
        )

        with patch.object(rc, "_get_project_tools_override", return_value={}):
            with patch.object(rc, "_get_project_integration_tools", return_value=[]):
                tool_config = await rc._get_agent_tools(session=None)

        tool = tool_config.identifiers[0]
        assert tool.args["transfer_destinations"] == {}

    @pytest.mark.asyncio
    async def test_livekit_filtered_on_non_voice_channel(self) -> None:
        """livekit_tool is filtered out for non-voice channels."""
        rc = _make_raw_config(
            "livekit_tool",
            tool_args={},
            channel=Channel.SMS,
        )

        async def mock_populate(tool_args, session=None):
            updated = tool_args.copy()
            updated.pop("transfer_destinations", None)
            updated["transfer_destinations"] = {"general": "+15559876543"}
            return updated

        with patch.object(
            rc, "_populate_transfer_tool_args", side_effect=mock_populate
        ):
            with patch.object(rc, "_get_project_tools_override", return_value={}):
                with patch.object(
                    rc, "_get_project_integration_tools", return_value=[]
                ):
                    tool_config = await rc._get_agent_tools(session=None)

        # Filtered out — no tools returned
        assert len(tool_config.identifiers) == 0
