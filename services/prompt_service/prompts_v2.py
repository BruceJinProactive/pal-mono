"""
PromptFactoryV2: YAML-based prompt management system

This module provides a more flexible prompt factory that loads prompts from YAML files,
allowing for easier management and updates without code changes.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from uuid import UUID

import yaml

from db.tables.types import Channel
from utils.log import logger


@dataclass
class Prompt:
    """Prompt configuration with optional filtering criteria"""

    id: str
    title: str
    instructions: str
    channels: Optional[list[Channel]] = None


class PromptFactoryV2:
    """
    YAML-based prompt factory with database override support.

    Loads prompts from YAML files in the same directory as this module.
    Provides channel-based filtering with optional database overrides per agent.
    """

    _cached_prompts: list[Prompt] = []
    _is_loaded = False
    _prompt_dir = Path(__file__).parent  # Always use same directory

    def __init__(self):
        # Load prompts only once at class level
        if not PromptFactoryV2._is_loaded:
            self._load_prompts()
            PromptFactoryV2._is_loaded = True

        # Each instance gets a reference to the shared cache
        self.registry = PromptFactoryV2._cached_prompts

    def _load_prompts(self) -> None:
        """Load prompts from YAML files - only runs once"""
        PromptFactoryV2._cached_prompts.clear()

        # Check if prompt directory exists
        if not PromptFactoryV2._prompt_dir.exists():
            logger.warning(
                f"Prompt directory {PromptFactoryV2._prompt_dir} does not exist. "
                "Creating with empty configuration."
            )
            return

        # Load all YAML files from the prompts directory
        yaml_files = list(PromptFactoryV2._prompt_dir.glob("*.yml"))

        if not yaml_files:
            logger.warning(f"No YAML files found in {PromptFactoryV2._prompt_dir}")
            return

        for yaml_file in sorted(yaml_files):  # Sort for consistent loading order
            try:
                self._load_yaml_file(yaml_file)
            except Exception as e:
                logger.error(f"Failed to load prompt file {yaml_file}: {e}")
                continue

        logger.info(
            f"Loaded {len(PromptFactoryV2._cached_prompts)} prompts from {len(yaml_files)} YAML files"
        )

    def _load_yaml_file(self, file_path: Path) -> None:
        """Load prompts from a single YAML file"""
        with open(file_path, "r") as f:
            data = yaml.safe_load(f)

        if not data or "prompts" not in data:
            logger.warning(f"No prompts found in {file_path}")
            return

        for prompt_data in data["prompts"]:
            try:
                # Convert string types to enums if needed
                if "channels" in prompt_data and prompt_data["channels"]:
                    prompt_data["channels"] = [
                        Channel[ch] if isinstance(ch, str) else ch
                        for ch in prompt_data["channels"]
                    ]

                prompt = Prompt(**prompt_data)
                self._register(prompt)

            except Exception as e:
                logger.error(
                    f"Failed to parse prompt in {file_path}: {e}\n"
                    f"Prompt data: {prompt_data}"
                )
                continue

    def _register(self, prompt: Prompt) -> None:
        """Register a prompt in the factory"""
        # Check for duplicate IDs
        existing_ids = {p.id for p in PromptFactoryV2._cached_prompts}
        if prompt.id in existing_ids:
            logger.warning(f"Overwriting existing prompt with ID: {prompt.id}")
            PromptFactoryV2._cached_prompts = [
                p for p in PromptFactoryV2._cached_prompts if p.id != prompt.id
            ]

        PromptFactoryV2._cached_prompts.append(prompt)

    def build(
        self,
        channel: Channel,
        agent_id: Optional[UUID] = None,
    ) -> list[tuple[str, str]]:
        """
        Build the final list of prompts by merging factory prompts with database prompts.

        Args:
            channel: Communication channel (SMS, VOICE, etc.)
            agent_id: Agent ID for querying database prompts (optional)

        Returns:
            List of (title, instructions) tuples for the final prompts
        """
        # Filter factory prompts based on channel
        selected_factory_prompts = []
        for prompt in self.registry:
            if prompt.channels is not None and channel not in prompt.channels:
                continue
            selected_factory_prompts.append(prompt)

        factory_prompts = []
        for prompt in selected_factory_prompts:
            factory_prompts.append((f"## {prompt.title}", prompt.instructions))

        return factory_prompts


# Simple module-level instance since configuration is fixed
prompt_factory_v2 = PromptFactoryV2()
