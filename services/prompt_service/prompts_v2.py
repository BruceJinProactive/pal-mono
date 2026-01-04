"""
PromptFactoryV2: YAML-based prompt management system

This module provides a more flexible prompt factory that loads prompts from YAML files,
allowing for easier management and updates without code changes.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Optional
from uuid import UUID

import yaml

from utils.log import logger


@dataclass
class Action:
    """Represents a single action within a capability"""

    action: str  # Action identifier (e.g., 'create_order', 'cancel_order')
    instruction: str  # The prompt/instruction text for this action
    channel: str = "ALL"  # Channel-specific override (SMS, VOICE, EMAIL, ALL)
    priority: int = 50  # Priority for ordering (lower = higher priority)


@dataclass
class Capability:
    """Represents a capability with its associated actions"""

    identifier: str  # Capability identifier (e.g., 'ordering', 'reservation')
    priority: int = 50  # Capability priority (lower = higher priority)
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
                        action = Action(
                            action=action_data["action"],
                            instruction=action_data.get("instruction", ""),
                            channel=action_data.get(
                                "channels", "ALL"
                            ),  # Note: YAML uses 'channels', we store as 'channel'
                            priority=action_data.get("priority", 50),
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

    def build(
        self,
        channel: Optional[str] = None,
        agent_id: Optional[UUID] = None,
    ) -> list[tuple[str, str]]:
        """
        Build the final list of prompts from default capabilities.

        Args:
            channel: Communication channel (SMS, VOICE, EMAIL, or None for all)
            agent_id: Agent ID for future database override support (optional)

        Returns:
            List of (title, instructions) tuples for the final prompts
        """
        prompts = []

        # Sort capabilities by priority
        sorted_capabilities = sorted(
            PromptFactoryV2._default_capabilities.values(), key=lambda c: c.priority
        )

        for capability in sorted_capabilities:
            if not capability.enabled:
                continue

            actions = capability.actions

            if channel:
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

            words = capability.identifier.replace("_", " ").title()
            title = f"{words} Instruction"

            prompts.append((title, combined_instructions))

        return prompts


prompt_factory_v2 = PromptFactoryV2()
