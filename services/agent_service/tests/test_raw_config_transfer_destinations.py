# pyright: reportGeneralTypeIssues=false, reportAttributeAccessIssue=false
"""Tests for transfer destination merging in _raw_config._get_agent_tools.

Verifies that livekit_transfer_tool preserves explicit destinations (e.g. SIP
URIs from raw_config) while merging in contact-derived phone numbers, while
vapi_tool continues to rebuild destinations from contacts only.
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


class TestLiveKitTransferDestinationMerge:
    """Explicit destinations in raw_config are preserved for livekit_transfer_tool."""

    @pytest.mark.asyncio
    async def test_explicit_sip_destinations_preserved(self) -> None:
        """SIP URIs from raw_config override contact-derived destinations."""
        explicit_destinations = {
            "complaint": "sip:complaints@sip.provider.com",
            "catering": "sip:catering@sip.provider.com",
        }
        rc = _make_raw_config(
            "livekit_transfer_tool",
            tool_args={"transfer_destinations": explicit_destinations},
        )

        # _populate_vapi_tool_args rebuilds from contacts — simulate it returning
        # contact-derived phone numbers for "general" and "complaint"
        contact_destinations = {
            "general": "+15559876543",
            "complaint": "+15550001111",
        }

        async def mock_populate(tool_args, session=None):
            updated = tool_args.copy()
            updated.pop("transfer_destinations", None)
            updated["transfer_destinations"] = contact_destinations.copy()
            updated["transfer_message"] = "Transferring you now."
            return updated

        with patch.object(rc, "_populate_vapi_tool_args", side_effect=mock_populate):
            with patch.object(rc, "_get_project_tools_override", return_value={}):
                with patch.object(
                    rc, "_get_project_integration_tools", return_value=[]
                ):
                    tool_config = await rc._get_agent_tools(session=None)

        tool = tool_config.identifiers[0]
        assert tool.tool_name == "livekit_transfer_tool"
        destinations = tool.args["transfer_destinations"]

        # Explicit SIP URIs win over contact-derived phone for same role
        assert destinations["complaint"] == "sip:complaints@sip.provider.com"
        assert destinations["catering"] == "sip:catering@sip.provider.com"
        # Contact-derived "general" is preserved (no explicit override)
        assert destinations["general"] == "+15559876543"

    @pytest.mark.asyncio
    async def test_no_explicit_destinations_uses_contacts_only(self) -> None:
        """When no explicit destinations in raw_config, contacts table drives all."""
        rc = _make_raw_config(
            "livekit_transfer_tool",
            tool_args={},
        )

        contact_destinations = {"general": "+15559876543", "faq": "+15550002222"}

        async def mock_populate(tool_args, session=None):
            updated = tool_args.copy()
            updated.pop("transfer_destinations", None)
            updated["transfer_destinations"] = contact_destinations.copy()
            return updated

        with patch.object(rc, "_populate_vapi_tool_args", side_effect=mock_populate):
            with patch.object(rc, "_get_project_tools_override", return_value={}):
                with patch.object(
                    rc, "_get_project_integration_tools", return_value=[]
                ):
                    tool_config = await rc._get_agent_tools(session=None)

        destinations = tool_config.identifiers[0].args["transfer_destinations"]
        assert destinations == {"general": "+15559876543", "faq": "+15550002222"}

    @pytest.mark.asyncio
    async def test_vapi_tool_does_not_preserve_explicit_destinations(self) -> None:
        """vapi_tool should NOT merge explicit destinations — contacts table only."""
        rc = _make_raw_config(
            "vapi_tool",
            tool_args={"transfer_destinations": {"complaint": "sip:x@provider.com"}},
        )

        contact_destinations = {"general": "+15559876543"}

        async def mock_populate(tool_args, session=None):
            updated = tool_args.copy()
            updated.pop("transfer_destinations", None)
            updated["transfer_destinations"] = contact_destinations.copy()
            return updated

        with patch.object(rc, "_populate_vapi_tool_args", side_effect=mock_populate):
            with patch.object(rc, "_get_project_tools_override", return_value={}):
                with patch.object(
                    rc, "_get_project_integration_tools", return_value=[]
                ):
                    tool_config = await rc._get_agent_tools(session=None)

        destinations = tool_config.identifiers[0].args["transfer_destinations"]
        # vapi_tool gets contacts only — explicit SIP URI was dropped
        assert destinations == {"general": "+15559876543"}
        assert "complaint" not in destinations

    @pytest.mark.asyncio
    async def test_livekit_filtered_on_non_voice_channel(self) -> None:
        """livekit_transfer_tool is filtered out for non-voice channels."""
        rc = _make_raw_config(
            "livekit_transfer_tool",
            tool_args={},
            channel=Channel.SMS,
        )

        async def mock_populate(tool_args, session=None):
            updated = tool_args.copy()
            updated.pop("transfer_destinations", None)
            updated["transfer_destinations"] = {"general": "+15559876543"}
            return updated

        with patch.object(rc, "_populate_vapi_tool_args", side_effect=mock_populate):
            with patch.object(rc, "_get_project_tools_override", return_value={}):
                with patch.object(
                    rc, "_get_project_integration_tools", return_value=[]
                ):
                    tool_config = await rc._get_agent_tools(session=None)

        # Filtered out — no tools returned
        assert len(tool_config.identifiers) == 0
