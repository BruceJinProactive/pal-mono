"""Tests for PromptFactoryV2 XML tag wrapping."""

import uuid

import pytest

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
