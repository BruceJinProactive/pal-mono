"""Tests for PromptFactoryV2 XML tag wrapping."""

import uuid

import pytest

from db.tables.types import Channel
from services.prompt_service.prompts_v2 import Action, Capability, PromptFactoryV2

TEST_AGENT_ID = uuid.uuid4()


def _make_cap(identifier, priority=10, enabled=True, instruction="Test."):
    return Capability(
        identifier=identifier,
        priority=priority,
        enabled=enabled,
        actions=[
            Action(
                action="act",
                instruction=instruction,
                channel="ALL",
                priority=10,
                enabled=True,
            )
        ],
    )


class TestCapabilityXmlWrapping:
    """Test that capabilities are wrapped in XML tags."""

    @pytest.mark.asyncio
    async def test_build_wraps_capability_in_xml_tags(self):
        """Capability instructions should be wrapped in <identifier> XML tags."""
        factory = PromptFactoryV2()
        test_cap = _make_cap("test_cap", instruction="Do the thing.")
        original = PromptFactoryV2._default_capabilities.copy()
        PromptFactoryV2._default_capabilities = {"test_cap": test_cap}
        try:
            prompts = await factory.build(
                agent_id=TEST_AGENT_ID, channel=None, session=None
            )
            assert len(prompts) == 1
            title, content = prompts[0]
            assert title == ""
            assert content.startswith("<test_cap>")
            assert content.endswith("</test_cap>")
            assert "Do the thing." in content
        finally:
            PromptFactoryV2._default_capabilities = original

    @pytest.mark.asyncio
    async def test_build_multiple_capabilities_sorted_by_priority(self):
        """Capabilities should be sorted by priority and each XML-wrapped."""
        factory = PromptFactoryV2()
        original = PromptFactoryV2._default_capabilities.copy()
        PromptFactoryV2._default_capabilities = {
            "alpha": _make_cap("alpha", priority=20),
            "beta": _make_cap("beta", priority=10),
        }
        try:
            prompts = await factory.build(
                agent_id=TEST_AGENT_ID, channel=None, session=None
            )
            assert len(prompts) == 2
            # Beta (priority 10) should come before Alpha (priority 20)
            assert "<beta>" in prompts[0][1]
            assert "<alpha>" in prompts[1][1]
        finally:
            PromptFactoryV2._default_capabilities = original

    @pytest.mark.asyncio
    async def test_disabled_capability_not_included(self):
        """Disabled capabilities should not appear in output."""
        factory = PromptFactoryV2()
        original = PromptFactoryV2._default_capabilities.copy()
        PromptFactoryV2._default_capabilities = {
            "off": _make_cap("off", enabled=False),
        }
        try:
            prompts = await factory.build(
                agent_id=TEST_AGENT_ID, channel=None, session=None
            )
            assert len(prompts) == 0
        finally:
            PromptFactoryV2._default_capabilities = original

    def test_all_channel_db_action_overrides_same_action_channel_default(self) -> None:
        """A DB ALL-channel override should replace same-action channel defaults."""
        factory = PromptFactoryV2()
        default_capability = Capability(
            identifier="call_transfer",
            priority=90,
            enabled=True,
            actions=[
                Action(
                    action="handle_call_transfer",
                    instruction="Default transfer prompt.",
                    channel=Channel.VOICE,
                    priority=90,
                    enabled=True,
                )
            ],
        )
        db_capability = Capability(
            identifier="call_transfer",
            priority=90,
            enabled=True,
            actions=[
                Action(
                    action="handle_call_transfer",
                    instruction="Custom transfer prompt.",
                    channel="ALL",
                    priority=90,
                    enabled=True,
                )
            ],
        )

        merged = factory._merge_capabilities(
            {"call_transfer": default_capability},
            {"call_transfer": db_capability},
        )

        actions = merged["call_transfer"].actions
        assert len(actions) == 1
        assert actions[0].instruction == "Custom transfer prompt."
        assert actions[0].channel == "ALL"

    def test_exact_channel_db_action_overrides_same_action_default(self) -> None:
        """A DB action with the same channel should replace the default action."""
        factory = PromptFactoryV2()
        default_capability = Capability(
            identifier="call_transfer",
            priority=90,
            enabled=True,
            actions=[
                Action(
                    action="handle_call_transfer",
                    instruction="Default transfer prompt.",
                    channel=Channel.VOICE,
                    priority=90,
                    enabled=True,
                )
            ],
        )
        db_capability = Capability(
            identifier="call_transfer",
            priority=90,
            enabled=True,
            actions=[
                Action(
                    action="handle_call_transfer",
                    instruction="Custom voice transfer prompt.",
                    channel=Channel.VOICE,
                    priority=90,
                    enabled=True,
                )
            ],
        )

        merged = factory._merge_capabilities(
            {"call_transfer": default_capability},
            {"call_transfer": db_capability},
        )

        actions = merged["call_transfer"].actions
        assert len(actions) == 1
        assert actions[0].instruction == "Custom voice transfer prompt."
        assert actions[0].channel == Channel.VOICE

    def test_unmatched_default_action_is_preserved_after_db_override(self) -> None:
        """Defaults without a matching DB action should remain in the merged output."""
        factory = PromptFactoryV2()
        default_capability = Capability(
            identifier="general",
            priority=10,
            enabled=True,
            actions=[
                Action(
                    action="provide_store_hours",
                    instruction="Default hours prompt.",
                    channel="ALL",
                    priority=10,
                    enabled=True,
                ),
                Action(
                    action="provide_location",
                    instruction="Default location prompt.",
                    channel="ALL",
                    priority=20,
                    enabled=True,
                ),
            ],
        )
        db_capability = Capability(
            identifier="general",
            priority=10,
            enabled=True,
            actions=[
                Action(
                    action="provide_store_hours",
                    instruction="Custom hours prompt.",
                    channel="ALL",
                    priority=10,
                    enabled=True,
                )
            ],
        )

        merged = factory._merge_capabilities(
            {"general": default_capability},
            {"general": db_capability},
        )

        instructions = [action.instruction for action in merged["general"].actions]
        assert instructions == ["Custom hours prompt.", "Default location prompt."]
