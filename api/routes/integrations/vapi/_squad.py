import json
import os
from typing import Any, List

from agent.config import (
    AgentConfig,
    LanguageAssistantMultilingConfig,
    MultilingualSquadConfig,
)
from utils.log import logger

from ._constants import DEFAULT_MULTILINGUAL_SQUAD_CONFIG, DEFAULT_SILENCE_TIMEOUT
from ._utils import add_voice_speed_if_supported
from .schema import (
    AssistantDestination,
    CallerInfo,
    SquadConfig,
    SquadMember,
    VAPIAssistant,
)

# ============================================================================
# EXCEPTIONS
# ============================================================================


class SquadCreationError(Exception):
    """Exception raised when squad creation fails."""

    pass


# ============================================================================
# ASSISTANT FACTORIES
# ============================================================================


class BaseAssistantFactory:
    """Base factory for creating VAPI assistants."""

    def __init__(self, agent_config: AgentConfig):
        self.agent_config = agent_config

    def _get_background_sound(self) -> str:
        """Determine background sound setting."""
        return (
            "office"
            if hasattr(self.agent_config.voice_config, "background_noise")
            and self.agent_config.voice_config.background_noise
            else "off"
        )

    def _add_background_denoising(self, assistant_config: dict[str, Any]) -> None:
        """Add background speech denoising configuration if available."""
        if (
            hasattr(self.agent_config.voice_config, "background_speech_denoising_plan")
            and self.agent_config.voice_config.background_speech_denoising_plan
        ):
            assistant_config["backgroundSpeechDenoisingPlan"] = (
                self.agent_config.voice_config.background_speech_denoising_plan.model_dump(
                    exclude_none=True
                )
            )


class TriageAssistantFactory(BaseAssistantFactory):
    """Factory for creating triage assistants."""

    def create(
        self,
        squad_config: MultilingualSquadConfig,
        account_display_name: str,
        speech_rate: Any,
    ) -> VAPIAssistant:
        """Create a triage assistant."""
        triage_config = squad_config.triage_assistant
        name = triage_config.name
        transcriber = {
            "provider": triage_config.transcriber.provider,
            "model": triage_config.transcriber.model,
            "language": triage_config.transcriber.language,
        }
        voice_config = {
            "provider": "cartesia",
            "voiceId": triage_config.voice.voice_id,
            "model": triage_config.voice.voice_model,
        }
        first_message = triage_config.first_message

        # Add speech rate if provided
        if speech_rate:
            voice_config = add_voice_speed_if_supported(voice_config, speech_rate)

        background_sound = self._get_background_sound()
        system_content = self._create_system_content(squad_config, account_display_name)

        assistant_config = {
            "name": name,
            "firstMessage": first_message,
            "transcriber": transcriber,
            "voice": voice_config,
            "backgroundSound": background_sound,
            "silenceTimeoutSeconds": DEFAULT_SILENCE_TIMEOUT,
            "backgroundDenoisingEnabled": True,
            "model": {
                "provider": "openai",
                "model": "gpt-4o",
                "messages": [{"role": "system", "content": system_content}],
            },
        }

        self._add_background_denoising(assistant_config)
        return VAPIAssistant(**assistant_config)

    def _create_system_content(
        self, squad_config: MultilingualSquadConfig, account_display_name: str
    ) -> str:
        """Create system content for triage assistant."""
        agent_name = self.agent_config.persona.name

        # Validate that the required languages for the hardcoded prompt exist
        required_languages = ["english", "spanish", "chinese"]
        missing_languages = [
            lang
            for lang in required_languages
            if lang not in squad_config.language_assistants
        ]
        if missing_languages:
            raise SquadCreationError(
                f"Missing required language configurations for triage assistant prompt: {', '.join(missing_languages)}"
            )

        english_assistant_name = squad_config.language_assistants[
            "english"
        ].assistant_name
        spanish_assistant_name = squad_config.language_assistants[
            "spanish"
        ].assistant_name
        chinese_assistant_name = squad_config.language_assistants[
            "chinese"
        ].assistant_name

        return f"""You are {agent_name}, the initial contact for {account_display_name}. 

Your ONLY responsibility is to:
1. Greet the customer warmly
2. Identify their preferred language (English, Spanish, or Chinese)
3. Transfer them to the appropriate language specialist

IMPORTANT TRANSFER RULES:
- For English speakers or English requests → transfer to {english_assistant_name}
- For Spanish speakers, "español", or Spanish requests → transfer to {spanish_assistant_name}  
- For Chinese speakers, "中文", Chinese characters, or Chinese requests → transfer to {chinese_assistant_name}

DO NOT attempt to help with their actual request - only identify language preference and transfer immediately."""


class LanguageAssistantFactory(BaseAssistantFactory):
    """Factory for creating language-specific assistants."""

    def create(
        self,
        language_config: LanguageAssistantMultilingConfig,
        language: str,
        account_display_name: str,
        speech_rate: Any,
        caller_info: CallerInfo,
        api_url: str,
    ) -> VAPIAssistant:
        """Create a language-specific assistant."""
        name = language_config.assistant_name
        transcriber = {
            "provider": language_config.transcriber.provider,
            "model": language_config.transcriber.model,
            "language": language_config.transcriber.language,
        }
        voice_config = {
            "provider": "cartesia",
            "voiceId": language_config.voice.voice_id,
            "model": language_config.voice.voice_model,
        }
        first_message = language_config.first_message

        # Add speech rate if provided
        if speech_rate:
            voice_config = add_voice_speed_if_supported(voice_config, speech_rate)

        background_sound = self._get_background_sound()
        system_content = self._create_system_content(language, account_display_name)

        assistant_config = {
            "name": name,
            "firstMessage": first_message,
            "transcriber": transcriber,
            "voice": voice_config,
            "backgroundSound": background_sound,
            "silenceTimeoutSeconds": DEFAULT_SILENCE_TIMEOUT,
            "backgroundDenoisingEnabled": True,
            "model": {
                "provider": "custom-llm",
                "url": f"{api_url}/v1",
                "model": json.dumps(caller_info.__dict__),
                "messages": [{"role": "system", "content": system_content}],
            },
        }

        self._add_background_denoising(assistant_config)
        return VAPIAssistant(**assistant_config)

    def _create_system_content(self, language: str, account_display_name: str) -> str:
        """Create language-specific system content."""
        agent_name = self.agent_config.persona.name
        agent_description = self.agent_config.persona.description or ""

        templates = {
            "english": f"You are {agent_name}, English customer support representative for {account_display_name}. {agent_description} \n\nKeep responses concise and helpful.",
            "spanish": f"Eres {agent_name}, representante de soporte al cliente en español para {account_display_name}. {agent_description} \n\nMantén las respuestas concisas y útiles.",
            "chinese": f"你是{agent_name}，{account_display_name}的中文客服代表。{agent_description} \n\n保持回答简洁有用。从现在开始必须用中文回复， 否则用户听不懂。",
        }

        return templates.get(language, templates["english"])


# ============================================================================
# SQUAD BUILDER
# ============================================================================


class SquadBuilder:
    """Builder for creating complete squad configurations."""

    def __init__(self, agent_config: AgentConfig):
        self.agent_config = agent_config
        self.squad_config = (
            agent_config.multiling_squad_config
            or MultilingualSquadConfig.model_validate(DEFAULT_MULTILINGUAL_SQUAD_CONFIG)
        )
        self.triage_factory = TriageAssistantFactory(agent_config)
        self.language_factory = LanguageAssistantFactory(agent_config)

    def build(
        self, account_display_name: str, caller_info: CallerInfo, api_url: str
    ) -> SquadConfig:
        """Build complete squad configuration."""
        try:
            speech_rate = getattr(self.agent_config.voice_config, "speech_rate", None)

            # Create all assistants
            assistants = self._create_all_assistants(
                account_display_name, speech_rate, caller_info, api_url
            )

            # Create transfer destinations
            destinations = self._create_transfer_destinations()

            # Build squad configuration
            members = [
                SquadMember(
                    assistant=assistants["triage"], assistantDestinations=destinations
                )
            ]
            for language_name in self.squad_config.language_assistants:
                members.append(SquadMember(assistant=assistants[language_name]))

            return SquadConfig(
                name=f"{account_display_name} Multilingual Support Squad",
                members=members,
            )

        except Exception as e:
            logger.error(f"Failed to build squad configuration: {str(e)}")
            raise SquadCreationError(f"Failed to build squad: {str(e)}") from e

    def _create_all_assistants(
        self,
        account_display_name: str,
        speech_rate: Any,
        caller_info: CallerInfo,
        api_url: str,
    ) -> dict[str, VAPIAssistant]:
        """Create all assistants for the squad."""
        assistants = {}

        # Create triage assistant
        assistants["triage"] = self.triage_factory.create(
            self.squad_config, account_display_name, speech_rate
        )

        # Create language assistants
        for (
            language_name,
            language_config,
        ) in self.squad_config.language_assistants.items():
            assistants[language_name] = self.language_factory.create(
                language_config,
                language_name,
                account_display_name,
                speech_rate,
                caller_info,
                api_url,
            )

        return assistants

    def _create_transfer_destinations(self) -> List[AssistantDestination]:
        """Create transfer destinations for the triage assistant."""
        destinations = []
        transfer_mode = self.squad_config.triage_assistant.transfer_mode

        for language_name in self.squad_config.language_assistants:
            config = self.squad_config.language_assistants[language_name]
            destinations.append(
                AssistantDestination(
                    assistantName=config.assistant_name,
                    message=config.transfer_message or "Connecting you now...",
                    description=config.transfer_description
                    or f"Transfer to {language_name} assistant",
                    transferMode=transfer_mode,  # type: ignore
                )
            )

        return destinations


# ============================================================================
# PUBLIC FUNCTIONS
# ============================================================================


def create_multilingual_squad(
    agent_config: AgentConfig,
    account_display_name: str,
    caller_info: dict[str, Any],
    call_id: str,
) -> dict[str, Any]:
    """
    Create a multilingual squad configuration with a triage assistant and language-specific assistants.
    By default, this supports English, Spanish, and Chinese. The supported languages can be configured
    via the `multiling_squad_config` in the agent configuration.

    The squad consists of:
    1. Language triage assistant (OpenAI GPT-4o, Google transcriber)
    2. Language-specific assistants (e.g., for English, Spanish, and Chinese)

    Args:
        agent_config: The agent configuration object
        account_display_name: The account display name
        caller_info: Information about the caller
        call_id: The call ID

    Returns:
        Squad configuration ready to be returned to VAPI
    """
    try:
        # Extract configuration
        api_url = os.environ.get("PAL_API_URL", "https://lat-api.palona.ai")

        # Structure caller info
        structured_caller_info = CallerInfo(
            sender_identifier=caller_info["sender_identifier"],
            recipient_identifier=caller_info["recipient_identifier"],
            call_id=call_id,
        )

        # Build squad using the builder pattern
        squad_builder = SquadBuilder(agent_config)
        squad_config = squad_builder.build(
            account_display_name, structured_caller_info, api_url
        )

        return {"squad": squad_config.model_dump()}

    except SquadCreationError:
        # Re-raise squad creation errors as-is
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating multilingual squad: {str(e)}")
        return {"error": f"Error creating multilingual squad: {str(e)}"}
