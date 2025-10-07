"""VAPI provider implementation."""

import json
import os
import re
from typing import Protocol, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from db.repositories.voice_config_repository import VoiceConfigRepositoryAsync
from db.tables.types import SpeechRate
from utils.log import logger

from ._utils import CALL_ANALYSIS_PROMPT

# Cartesia speed mapping for voice configuration
CARTESIA_SPEED_MAPPING = {
    SpeechRate.slowest: "slowest",
    SpeechRate.slower: "slow",
    SpeechRate.normal: "normal",
    SpeechRate.faster: "fast",
    SpeechRate.fastest: "fastest",
}


class VoiceConfigProtocol(Protocol):
    """Protocol defining the interface for voice configuration objects."""

    language: str
    voice_id: str
    first_message: str
    transfer_message: str
    replacements: dict
    background_sound: str
    speech_rate: SpeechRate


class VAPIProvider:
    """VAPI voice provider implementation."""

    def __init__(self):
        pass

    async def get_assistant_response(
        self,
        caller_info: dict,
        project_id: UUID,
        session: AsyncSession,
    ) -> dict:
        """
        Create assistant response for VAPI call.

        Args:
            caller_info: Dictionary containing caller information with keys:
                - sender_identifier: customer phone number
                - recipient_identifier: business phone number
                - call_id: unique call identifier
            project_id: The project identifier (UUID)
            session: The database session

        Returns:
            dict: Assistant response configuration for VAPI
        """
        try:
            call_id = caller_info.get("call_id")
            logger.debug(
                f"Creating assistant response for call {call_id} with caller info: {caller_info}"
            )

            # Check for fallback environment variables
            use_fallback_transcriber = (
                os.environ.get("USE_FALLBACK_TRANSCRIBER", "false").lower() == "true"
            )
            use_fallback_voice = (
                os.environ.get("USE_FALLBACK_VOICE", "false").lower() == "true"
            )

            # Get voice configurations
            voice_configs = await self._get_voice_configs(session, project_id)

            # Use fallback config if either environment variable is true
            if use_fallback_transcriber or use_fallback_voice:
                return self._create_fallback_assistant_config(
                    use_fallback_transcriber,
                    use_fallback_voice,
                    voice_configs,
                    caller_info,
                )

            # Create assistant configuration
            return self._create_assistant_config(voice_configs, caller_info)

        except Exception as e:
            logger.error(f"Error creating assistant response: {str(e)}")
            return {"error": str(e)}

    async def _get_voice_configs(
        self, session: AsyncSession, project_id: UUID
    ) -> list[VoiceConfigProtocol]:
        """Get voice configurations for the project."""
        voice_repo = VoiceConfigRepositoryAsync(session)
        voice_configs = await voice_repo.get_voice_configs_by_project(project_id)

        if not voice_configs:
            logger.error(f"No voice configuration found for project {project_id}")
            raise ValueError(f"No voice configuration found for project {project_id}")

        # Cast to protocol - VoiceConfig objects satisfy the VoiceConfigProtocol interface
        return cast(list[VoiceConfigProtocol], voice_configs)

    def _create_transcriber(self, language: str) -> dict:
        """Create transcriber configuration based on language."""
        # Map human-readable language names to transcriber configs
        language_configs = {
            "english": {"model": "nova-3", "language": "en-US", "provider": "deepgram"},
            "spanish": {"model": "nova-2", "language": "es", "provider": "deepgram"},
            "chinese": {
                "model": "nova-2",
                "language": "zh-CN",
                "provider": "deepgram",
            },
            "triage": {
                "model": "gemini-2.5-flash",
                "language": "Multilingual",
                "provider": "google",
            },
        }

        # Return specific config if language is found, otherwise default to English
        return language_configs.get(language.lower(), language_configs["english"])

    def _create_voice(self, voice_config: VoiceConfigProtocol) -> dict:
        """Create voice configuration based on voice_config."""
        # Base voice configuration
        vapi_voice_config = {
            "provider": "cartesia",
            "voiceId": voice_config.voice_id,
            "model": "sonic-2",
            "experimentalControls": {
                "speed": CARTESIA_SPEED_MAPPING.get(voice_config.speech_rate, "normal")
            },
        }

        # Add chunkPlan with formatPlan only if replacements exist
        if voice_config.replacements:
            chunk_plan = {"formatPlan": {"replacements": []}}

            for key, value in voice_config.replacements.items():
                # Check if key contains "wordy" characters (Latin letters/numbers)
                # For such keys, use word boundaries (\b)
                # For non-wordy keys (like Chinese ideographs), match literal token
                if re.search(r"[a-zA-Z0-9]", str(key)):
                    # Contains wordy characters - use word boundaries
                    pattern = f"(?i)\\b{str(key)}\\b"
                else:
                    # Non-wordy characters (like Chinese) - match literally without boundaries
                    pattern = f"(?i){str(key)}"

                chunk_plan["formatPlan"]["replacements"].append(
                    {"type": "regex", "regex": pattern, "value": value}
                )

            vapi_voice_config["chunkPlan"] = chunk_plan

        return vapi_voice_config

    def _create_start_speaking_plan(self, language: str) -> dict:
        """Create startSpeakingPlan configuration based on language."""
        if language.lower() == "english":
            return {"waitSeconds": 0.1, "smartEndpointingPlan": {"provider": "livekit"}}
        else:
            return {
                "transcriptionEndpointingPlan": {
                    "onPunctuationSeconds": 0.1,
                    "onNoPunctuationSeconds": 0.3,
                    "onNumberSeconds": 0.5,
                },
                "waitSeconds": 0.1,
            }

    def _get_analysis_plan(self) -> dict:
        """
        Returns the complete analysis plan configuration for VAPI structured data extraction.

        This function creates the analysisPlan configuration that includes:
        - Structured data plan with the call analysis prompt
        - System and user message templates
        - Timeout configuration

        Returns:
            dict: Complete analysis plan configuration ready for VAPI
        """
        return {
            "structuredDataPlan": {
                "enabled": True,
                "messages": [
                    {
                        "role": "system",
                        "content": CALL_ANALYSIS_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": "Here is the transcript: {{transcript}}\n\nHere is the ended reason of the call: {{endedReason}}\n\nAnalyze this conversation and provide the structured data.",
                    },
                ],
                "timeoutSeconds": 15,
            }
        }

    def _create_assistant_config(
        self, voice_configs: list[VoiceConfigProtocol], caller_info: dict
    ) -> dict:
        """Create assistant configuration based on number of voice configs."""
        # Separate triage and non-triage configs
        triage_configs = [vc for vc in voice_configs if vc.language.lower() == "triage"]
        non_triage_configs = [
            vc for vc in voice_configs if vc.language.lower() != "triage"
        ]

        if not non_triage_configs:
            call_id = caller_info.get("call_id")
            logger.error(f"Missing language assistant config for call: {call_id}")
            raise ValueError("Missing language assistant config")

        if len(non_triage_configs) == 1:
            assistant_config = self._create_single_assistant_config(
                non_triage_configs[0], caller_info, only_assistant=True
            )
            return {"assistant": assistant_config}
        else:
            if not triage_configs:
                call_id = caller_info.get("call_id")
                logger.error(f"Missing triage assistant config for call: {call_id}")
                raise ValueError("Missing triage assistant config")

            return self._create_multi_assistant_config(
                non_triage_configs, triage_configs, caller_info
            )

    def _create_single_assistant_config(
        self, voice_config: VoiceConfigProtocol, caller_info: dict, only_assistant: bool
    ) -> dict:
        """Create single assistant configuration."""
        # Check if language is 'triage' which is not allowed for single assistant
        if voice_config.language.lower() == "triage":
            call_id = caller_info.get("call_id")
            logger.error(
                f"Cannot create single assistant with 'triage' language for call {call_id}"
            )
            raise ValueError(
                "Single assistant configuration cannot use 'triage' language"
            )

        # Use first_message from voice_config or create default greeting
        if voice_config.first_message:
            greeting = voice_config.first_message
        else:
            greeting = "Hi, this is a voice ai assistant. How can I help you today?"

        # Create transcriber configuration based on language
        transcriber = self._create_transcriber(voice_config.language)

        # Create voice configuration based on voice_config
        voice = self._create_voice(voice_config)

        background_sound = voice_config.background_sound

        # Prepare assistant configuration
        api_url = os.environ.get("PAL_API_URL", "https://lat-api.palona.ai")
        assistant_config = {
            "name": f"{voice_config.language.lower()}_assistant",
            "firstMessage": greeting,
            "transcriber": transcriber,
            "model": {
                "provider": "custom-llm",
                "url": f"{api_url}/v1",
                "model": json.dumps(caller_info),
            },
            "voice": voice,
            "backgroundSound": background_sound,
            "silenceTimeoutSeconds": 60,
            "backgroundSpeechDenoisingPlan": {"smartDenoisingPlan": {"enabled": True}},
            "startSpeakingPlan": self._create_start_speaking_plan(
                voice_config.language
            ),
            "firstMessageInterruptionsEnabled": not only_assistant,
            "firstMessageMode": "assistant-speaks-first",
            "analysisPlan": self._get_analysis_plan(),
        }

        return assistant_config

    def _create_triage_assistant(
        self,
        triage_config: VoiceConfigProtocol,
        non_triage_configs: list[VoiceConfigProtocol],
        caller_info: dict,
    ) -> dict:
        """Create triage assistant configuration."""
        # Use first_message from triage_config or create default greeting
        if triage_config.first_message:
            greeting = triage_config.first_message
        else:
            greeting = "Hi, this is a voice ai assistant. How can I help you today?"

        # Create transcriber configuration for triage (multilingual)
        transcriber = self._create_transcriber(triage_config.language)

        # Create voice configuration for triage
        voice = self._create_voice(triage_config)

        background_sound = triage_config.background_sound

        # Create system content for triage assistant
        system_content = self._create_system_content(non_triage_configs)

        # Prepare triage assistant configuration
        triage_assistant_config = {
            "name": "triage_assistant",
            "firstMessage": greeting,
            "transcriber": transcriber,
            "model": {
                "provider": "openai",
                "model": "gpt-4o",
                "messages": [{"role": "system", "content": system_content}],
            },
            "voice": voice,
            "backgroundSound": background_sound,
            "silenceTimeoutSeconds": 60,
            "firstMessageInterruptionsEnabled": False,
            "firstMessageMode": "assistant-speaks-first",
            "backgroundSpeechDenoisingPlan": {"smartDenoisingPlan": {"enabled": True}},
            "startSpeakingPlan": self._create_start_speaking_plan(
                triage_config.language
            ),
        }

        return triage_assistant_config

    def _create_system_content(
        self, non_triage_configs: list[VoiceConfigProtocol]
    ) -> str:
        """Create system content for triage assistant."""
        # Build language list and transfer rules dynamically
        languages = [config.language.lower() for config in non_triage_configs]

        if not languages:
            raise ValueError("No languages provided in the voice configuration")

        language_list = (
            ", ".join(languages[:-1]) + f", or {languages[-1]}"
            if len(languages) > 1
            else languages[0]
        )

        transfer_rules = []
        for voice_config in non_triage_configs:
            language = voice_config.language.lower()
            assistant_name = f"{language}_assistant"
            transfer_rules.append(
                f"- For {language.title()} speakers or {language.title()} requests → transfer to {assistant_name}"
            )

        transfer_rules_text = "\n".join(transfer_rules)

        return f"""You are the initial contact assistant.

Your ONLY responsibility is to:
1. Greet the customer warmly
2. Identify their preferred language ({language_list})
3. Transfer them to the appropriate language specialist
4. If the user gives an request in English, transfer them to the English-speaking assistant.

IMPORTANT TRANSFER RULES:
{transfer_rules_text}

DO NOT attempt to help with their actual request - only identify language preference and transfer immediately."""

    def _create_transfer_destinations(
        self, non_triage_configs: list[VoiceConfigProtocol]
    ) -> list[dict]:
        """Create transfer destinations for triage assistant."""
        destinations = []

        for voice_config in non_triage_configs:
            language = voice_config.language.lower()
            assistant_name = f"{language}_assistant"

            # Use transfer_message from voice_config or create default
            transfer_message = voice_config.transfer_message or "One second."

            # Create detailed description based on language
            description = self._create_transfer_description(language)

            destination = {
                "assistantName": assistant_name,
                "message": transfer_message,
                "description": description,
                "transferMode": "swap-system-message-in-history",
                "type": "assistant",
            }
            destinations.append(destination)

        return destinations

    def _create_transfer_description(self, language: str) -> str:
        """Create detailed transfer description for each language."""
        descriptions = {
            "english": 'Transfer to English-speaking assistant when customer prefers English, says "english", speaks English, or uses/requests any language other than those explicitly supported.',
            "spanish": 'Transfer to Spanish-speaking assistant when customer prefers Spanish, says "español", or uses Spanish language.',
            "chinese": 'Transfer to Chinese-speaking assistant when customer prefers Chinese, says "中文", uses Chinese characters, or indicates Chinese language preference.',
        }

        # Return specific description or create a generic one
        return descriptions.get(
            language,
            f"Transfer to {language.title()}-speaking assistant when customer prefers {language.title()} language or indicates {language.title()} language preference.",
        )

    def _create_multi_assistant_config(
        self,
        non_triage_configs: list[VoiceConfigProtocol],
        triage_configs: list[VoiceConfigProtocol],
        caller_info: dict,
    ) -> dict:
        """Create multi-assistant configuration (squad)."""
        # Create triage assistant
        triage_assistant = self._create_triage_assistant(
            triage_configs[0], non_triage_configs, caller_info
        )

        # Create language assistants
        language_assistants = []
        for voice_config in non_triage_configs:
            # Create individual assistant for each non-triage voice config
            assistant = self._create_single_assistant_config(
                voice_config, caller_info, only_assistant=False
            )
            language_assistants.append(assistant)

        # Create transfer destinations for the triage assistant
        assistant_destinations = self._create_transfer_destinations(non_triage_configs)

        return self._build_squad_config(
            triage_assistant, language_assistants, assistant_destinations
        )

    def _build_squad_config(
        self,
        triage_assistant: dict,
        language_assistants: list[dict],
        assistant_destinations: list[dict],
    ) -> dict:
        """Build the complete squad configuration with triage and language assistants."""
        # Build squad members - triage assistant first with assistantDestinations, then language assistants
        members = []

        # Add triage assistant as first member with assistantDestinations if provided
        triage_member: dict = {"assistant": triage_assistant}
        if assistant_destinations:
            triage_member["assistantDestinations"] = assistant_destinations
        members.append(triage_member)

        # Add language assistants as remaining members
        for assistant in language_assistants:
            members.append({"assistant": assistant})

        # Return complete squad configuration
        squad_config = {
            "name": "Multilingual Support Squad",
            "members": members,
        }

        return {"squad": squad_config}

    def _create_fallback_assistant_config(
        self,
        use_fallback_transcriber: bool,
        use_fallback_voice: bool,
        voice_configs: list[VoiceConfigProtocol],
        caller_info: dict,
    ) -> dict:
        """Create fallback assistant configuration with optional voice config data.

        Args:
            use_fallback_transcriber: Whether to use fallback transcriber configuration
            use_fallback_voice: Whether to use fallback voice configuration
            voice_configs: List of voice configurations to use for non-fallback settings
            caller_info: Dictionary containing caller information
        """
        # Find English voice config or use defaults
        english_config = None
        for config in voice_configs:
            if config.language.lower() == "english":
                english_config = config
                break

        # Use voice config data if available, otherwise defaults
        if english_config:
            greeting = (
                english_config.first_message
                or "Hi, this is a voice ai assistant. How can I help you today?"
            )
            background_sound = english_config.background_sound
        else:
            greeting = "Hi, this is a voice ai assistant. How can I help you today?"
            background_sound = "office"

        language = "english"

        # Create transcriber configuration - use fallback if specified
        if use_fallback_transcriber:
            # Default fallback transcriber configuration
            transcriber = {
                "model": "gemini-2.5-flash-lite",
                "language": "English",
                "provider": "google",
            }
        else:
            transcriber = self._create_transcriber(language)

        # Create voice configuration - use voice config if available and not using fallback
        if english_config and not use_fallback_voice:
            voice = self._create_voice(english_config)
        else:
            # Default fallback voice configuration
            voice = {
                "provider": "11labs",
                "voiceId": "cgSgspJ2msm6clMCkdW9",
                "model": "eleven_turbo_v2",
            }

        # Prepare assistant configuration
        api_url = os.environ.get("PAL_API_URL", "https://lat-api.palona.ai")
        assistant_config = {
            "name": "fallback_assistant",
            "firstMessage": greeting,
            "transcriber": transcriber,
            "model": {
                "provider": "custom-llm",
                "url": f"{api_url}/v1",
                "model": json.dumps(caller_info),
            },
            "voice": voice,
            "backgroundSound": background_sound,
            "silenceTimeoutSeconds": 60,
            "backgroundSpeechDenoisingPlan": {"smartDenoisingPlan": {"enabled": True}},
            "startSpeakingPlan": self._create_start_speaking_plan(language),
            "firstMessageInterruptionsEnabled": True,
            "firstMessageMode": "assistant-speaks-first",
            "analysisPlan": self._get_analysis_plan(),
        }

        return {"assistant": assistant_config}
