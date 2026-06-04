"""Tests for the empty adora capability scaffold.

PR 1 of the adora capability split (PAL-11021). The `adora` capability is
introduced with no actions; this verifies that its presence does not change
any agent's assembled prompt.
"""

import uuid

import pytest

from services.prompt_service.prompts_v2 import Action, Capability, PromptFactoryV2

TEST_AGENT_ID = uuid.uuid4()


def _ordering_cap() -> Capability:
    return Capability(
        identifier="ordering",
        priority=20,
        enabled=True,
        actions=[
            Action(
                action="create_order_adora",
                instruction="Create the order.",
                channel="ALL",
                priority=10,
                enabled=True,
            )
        ],
    )


def _empty_adora_cap(enabled: bool = True) -> Capability:
    return Capability(
        identifier="adora",
        priority=95,
        enabled=enabled,
        actions=[],
    )


class TestEmptyAdoraCapabilityScaffold:
    """Empty adora capability must not appear in the assembled prompt."""

    @pytest.mark.asyncio
    async def test_empty_adora_not_in_build_when_only_adora_loaded(self) -> None:
        factory = PromptFactoryV2()
        original = PromptFactoryV2._default_capabilities.copy()
        PromptFactoryV2._default_capabilities = {"adora": _empty_adora_cap()}
        try:
            prompts = await factory.build(
                agent_id=TEST_AGENT_ID, channel=None, session=None
            )
            assert prompts == []
        finally:
            PromptFactoryV2._default_capabilities = original

    @pytest.mark.asyncio
    async def test_empty_adora_alongside_ordering_does_not_emit_tag(self) -> None:
        factory = PromptFactoryV2()
        original = PromptFactoryV2._default_capabilities.copy()
        PromptFactoryV2._default_capabilities = {
            "ordering": _ordering_cap(),
            "adora": _empty_adora_cap(),
        }
        try:
            prompts = await factory.build(
                agent_id=TEST_AGENT_ID, channel=None, session=None
            )
            assert len(prompts) == 1
            _, content = prompts[0]
            assert "<ordering>" in content
            assert "Create the order." in content
            assert "<adora>" not in content
            assert "</adora>" not in content
        finally:
            PromptFactoryV2._default_capabilities = original

    @pytest.mark.asyncio
    async def test_empty_adora_disabled_via_default_also_skipped(self) -> None:
        """Even if the capability is left disabled (YAML default state), build skips it."""
        factory = PromptFactoryV2()
        original = PromptFactoryV2._default_capabilities.copy()
        PromptFactoryV2._default_capabilities = {
            "ordering": _ordering_cap(),
            "adora": _empty_adora_cap(enabled=False),
        }
        try:
            prompts = await factory.build(
                agent_id=TEST_AGENT_ID, channel=None, session=None
            )
            assert len(prompts) == 1
            _, content = prompts[0]
            assert "<adora>" not in content
        finally:
            PromptFactoryV2._default_capabilities = original
