"""
PromptFactoryV2: YAML-based prompt management system

This module provides a more flexible prompt factory that loads prompts from YAML files,
allowing for easier management and updates without code changes.
"""

import hashlib
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Literal, Optional, Union
from uuid import UUID

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from db.tables.types import Channel
from utils.log import logger

# Type for channel values - either a Channel enum or "ALL" for wildcard
ChannelType = Union[Channel, Literal["ALL"]]


def parse_channel(channel_str: str) -> ChannelType:
    """Convert a string to a Channel enum or 'ALL'."""
    if channel_str == "ALL":
        return "ALL"

    # Try to match with enum values (case-insensitive)
    channel_upper = channel_str.upper()
    for ch in Channel:
        if ch.value.upper() == channel_upper:
            return ch

    # Default to ALL if unrecognized
    logger.warning(f"Unknown channel '{channel_str}', defaulting to 'ALL'")
    return "ALL"


@dataclass
class Action:
    """Represents a single action within a capability"""

    action: str  # Action identifier (e.g., 'create_order', 'cancel_order')
    instruction: str  # The prompt/instruction text for this action
    channel: ChannelType = "ALL"  # Channel-specific override (SMS, VOICE, EMAIL, ALL)
    priority: int = 50  # Prompt position (higher = later = stronger)
    enabled: bool = True  # Whether this action is enabled (defaults to True)


@dataclass
class Capability:
    """Represents a capability with its associated actions"""

    identifier: str  # Capability identifier (e.g., 'ordering', 'reservation')
    priority: int = 50  # Prompt position (higher = later = stronger)
    enabled: bool = True
    actions: list[Action] = field(default_factory=list)


class PromptFactoryV2:
    """
    Capability-based prompt factory with database override support.

    Loads capability definitions from YAML files in the capabilities directory.
    Provides channel-based filtering with optional database overrides per agent.
    """

    _default_capabilities: ClassVar[dict[str, Capability]] = (
        {}
    )  # Cache for default capabilities loaded from YAML
    _is_loaded: ClassVar[bool] = False
    _capabilities_dir: ClassVar[Path] = (
        Path(__file__).parent / "capabilities"
    )  # Capabilities directory

    def __init__(self):
        # Load capabilities only once at class level
        if not PromptFactoryV2._is_loaded:
            self._load_capabilities()
            PromptFactoryV2._is_loaded = True

    def _load_capabilities(self) -> None:
        """Load capabilities from YAML files - only runs once"""
        PromptFactoryV2._default_capabilities.clear()

        if not PromptFactoryV2._capabilities_dir.exists():
            logger.warning(
                f"Capabilities directory {PromptFactoryV2._capabilities_dir} does not exist. "
                "Creating with empty configuration."
            )
            return

        # Load all YAML files from the capabilities directory
        yaml_files = list(PromptFactoryV2._capabilities_dir.glob("*.yaml"))

        if not yaml_files:
            logger.warning(
                f"No YAML files found in {PromptFactoryV2._capabilities_dir}"
            )
            return

        for yaml_file in sorted(yaml_files):  # Sort for consistent loading order
            try:
                self._load_capability_file(yaml_file)
            except Exception as e:
                logger.error(f"Failed to load capability file {yaml_file}: {e}")
                continue

        logger.info(
            f"Loaded {len(PromptFactoryV2._default_capabilities)} capabilities from {len(yaml_files)} YAML files"
        )

    def _load_capability_file(self, file_path: Path) -> None:
        """Load a capability and its actions from a single YAML file"""
        with open(file_path, "r") as f:
            data = yaml.safe_load(f)

        if not data or "capability" not in data:
            logger.warning(f"No capability definition found in {file_path}")
            return

        try:
            # Parse capability metadata
            cap_data = data["capability"]
            capability = Capability(
                identifier=cap_data["capability_identifier"],
                priority=cap_data.get("priority", 50),
                enabled=cap_data.get("default_enabled", False),
                actions=[],
            )

            # Parse actions if present
            if "actions" in data and data["actions"]:
                for action_data in data["actions"]:
                    try:
                        channel_str = action_data.get(
                            "channels", "ALL"
                        )  # YAML uses 'channels'
                        action = Action(
                            action=action_data["action"],
                            instruction=action_data.get("instruction", ""),
                            channel=parse_channel(channel_str),
                            priority=action_data.get("priority", 50),
                            enabled=action_data.get("enabled", False),
                        )
                        capability.actions.append(action)
                    except Exception as e:
                        logger.error(
                            f"Failed to parse action in {file_path}: {e}\n"
                            f"Action data: {action_data}"
                        )
                        continue

            self._register_capability(capability)

        except Exception as e:
            logger.error(
                f"Failed to parse capability in {file_path}: {e}\n"
                f"Capability data: {data}"
            )
            return

    def _register_capability(self, capability: Capability) -> None:
        """Register a capability in the factory"""
        # Check for duplicate capability identifiers
        if capability.identifier in PromptFactoryV2._default_capabilities:
            logger.warning(f"Overwriting existing capability: {capability.identifier}")

        PromptFactoryV2._default_capabilities[capability.identifier] = capability

    async def _get_db_overrides(
        self, agent_id: UUID, session: AsyncSession
    ) -> dict[str, Capability]:
        """
        Fetch capability and action overrides from database for an agent.

        Args:
            agent_id: UUID of the agent
            session: Database session

        Returns:
            Dictionary of capability identifier to Capability with DB overrides
        """
        try:
            # Import repositories here to avoid circular dependencies
            from db.repositories.agent_capability_repository import (
                AgentCapabilityRepositoryAsync,
            )
            from db.repositories.capability_action_repository import (
                CapabilityActionRepositoryAsync,
            )

            # Get agent capabilities
            agent_cap_repo = AgentCapabilityRepositoryAsync(session)
            agent_capabilities = await agent_cap_repo.get_by_agent(
                agent_id, enabled_only=False
            )

            if not agent_capabilities:
                return {}

            # Get actions for all capabilities
            capability_ids = [cap.id for cap in agent_capabilities]
            action_repo = CapabilityActionRepositoryAsync(session)
            actions_by_capability = await action_repo.get_actions_for_capabilities(
                capability_ids
            )

            # Build Capability objects from DB data
            db_capabilities = {}
            for agent_cap in agent_capabilities:
                # Create capability with DB settings
                capability = Capability(
                    identifier=agent_cap.capability_identifier,
                    priority=agent_cap.priority,
                    enabled=agent_cap.enabled,
                    actions=[],
                )

                # Add actions if present
                if agent_cap.id in actions_by_capability:
                    for db_action in actions_by_capability[agent_cap.id]:
                        action = Action(
                            action=db_action.action,
                            instruction=db_action.prompt,  # DB uses 'prompt' field
                            channel=parse_channel(db_action.channel),
                            priority=db_action.priority,
                            enabled=db_action.enabled,  # Preserve enabled state from DB
                        )
                        capability.actions.append(action)

                db_capabilities[capability.identifier] = capability

            return db_capabilities

        except Exception as e:
            logger.error(f"Failed to fetch DB overrides for agent {agent_id}: {e}")
            return {}

    def _merge_capabilities(
        self,
        default_capabilities: dict[str, Capability],
        db_overrides: dict[str, Capability],
    ) -> dict[str, Capability]:
        """
        Merge default capabilities with database overrides using action-level merging.

        For each DB override:
        1. If capability doesn't exist in defaults, add it
        2. If it exists:
           - Override priority and enabled state from DB
           - Merge actions: DB actions override matching default actions by name
           - Keep default actions that aren't overridden
           - Add new DB actions

        Args:
            default_capabilities: Default capabilities from YAML
            db_overrides: Database overrides

        Returns:
            Merged capabilities dictionary
        """
        # Start with a deep copy of defaults
        merged = deepcopy(default_capabilities)

        for cap_id, db_capability in db_overrides.items():
            if cap_id not in merged:
                # New capability from DB, add it entirely
                merged[cap_id] = deepcopy(db_capability)
            else:
                # Merge with existing capability
                default_cap = merged[cap_id]

                # Override capability-level settings
                default_cap.priority = db_capability.priority
                default_cap.enabled = db_capability.enabled

                # Merge actions
                # Create a dict of default actions by (action, channel) for easier lookup
                default_actions_map = {
                    (action.action, action.channel): action
                    for action in default_cap.actions
                }

                # Create a dict of DB actions
                db_actions_map = {
                    (action.action, action.channel): action
                    for action in db_capability.actions
                }
                db_all_channel_action_names = {
                    action.action
                    for action in db_capability.actions
                    if action.channel == "ALL"
                }

                # Build merged actions list
                merged_actions = []

                # Add/override with DB actions
                for key, db_action in db_actions_map.items():
                    merged_actions.append(deepcopy(db_action))

                # Add default actions that weren't overridden
                for key, default_action in default_actions_map.items():
                    if key in db_actions_map:
                        continue
                    if default_action.action in db_all_channel_action_names:
                        continue
                    merged_actions.append(deepcopy(default_action))

                default_cap.actions = merged_actions

        return merged

    async def build(
        self,
        agent_id: UUID,
        channel: Optional[Channel] = None,
        session: Optional[AsyncSession] = None,
    ) -> list[tuple[str, str]]:
        """
        Build the final list of prompts with optional database overrides.

        Args:
            agent_id: Agent ID for database override support
            channel: Communication channel enum (Channel.SMS, Channel.VOICE, etc.) or None for all
            session: Database session for fetching overrides (optional)

        Returns:
            List of (title, instructions) tuples for the final prompts
        """
        # Start with default capabilities
        capabilities = PromptFactoryV2._default_capabilities

        # Apply database overrides if agent_id and session provided
        if agent_id and session:
            db_overrides = await self._get_db_overrides(agent_id, session)
            if db_overrides:
                capabilities = self._merge_capabilities(
                    PromptFactoryV2._default_capabilities, db_overrides
                )

        prompts = []

        # Sort by priority (lower = earlier, higher = later/stronger)
        sorted_capabilities = sorted(capabilities.values(), key=lambda c: c.priority)

        for capability in sorted_capabilities:
            if not capability.enabled:
                continue

            actions = capability.actions

            # Filter out disabled actions
            actions = [action for action in actions if action.enabled]

            if channel:
                # Filter actions by channel - include if action is for ALL or matches the specific channel
                actions = [
                    action
                    for action in actions
                    if action.channel == "ALL" or action.channel == channel
                ]

            if not actions:
                continue

            sorted_actions = sorted(actions, key=lambda a: a.priority)

            action_instructions = []
            for action in sorted_actions:
                action_instructions.append(action.instruction)

            combined_instructions = "\n\n".join(action_instructions)

            # Wrap capability instructions in XML tags for clear section boundaries
            tag = capability.identifier
            wrapped = f"<{tag}>\n{combined_instructions}\n</{tag}>"

            prompts.append(("", wrapped))

        return prompts

    async def build_with_hash(
        self,
        agent_id: UUID,
        channel: Optional[Channel] = None,
        session: Optional[AsyncSession] = None,
    ) -> tuple[list[tuple[str, str]], str]:
        """
        Build prompts and return them along with a SHA-256 hash of the canonical text.

        Args:
            agent_id: Agent ID for database override support
            channel: Communication channel enum or None for all
            session: Database session for fetching overrides (optional)

        Returns:
            Tuple of (prompts, prompt_hash) where:
                - prompts is a list of (title, instructions) tuples
                - prompt_hash is the hex SHA-256 digest of the canonical prompt text
        """
        prompts = await self.build(agent_id=agent_id, channel=channel, session=session)
        canonical = "\n\n".join(
            f"{title}\n{instructions}" for title, instructions in prompts
        )
        prompt_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return prompts, prompt_hash


prompt_factory_v2 = PromptFactoryV2()
