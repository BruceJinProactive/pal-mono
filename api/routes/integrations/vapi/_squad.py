import json
import os
from typing import Any, Dict, List

from agent.config import (
    AgentConfig,
    AssistantDestination,
    CallerInfo,
    LanguageAssistantMultilingConfig,
    MultilingualSquadConfig,
    SquadConfig,
    SquadMember,
    VAPIAssistant,
    VoiceDecoderConfig,
)
from utils.log import logger

from ._constants import DEFAULT_MULTILINGUAL_SQUAD_CONFIG
from ._utils import add_voice_speed_if_supported

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

    def _add_background_denoising(self, assistant_config: dict[str, Any]) -> None:
        """Add background speech denoising configuration if available."""
        if (
            hasattr(self.agent_config.voice_config, "background_speech_denoising_plan")
            and self.agent_config.voice_config.background_speech_denoising_plan
        ):
            assistant_config["backgroundSpeechDenoisingPlan"] = (
                self.agent_config.voice_config.background_speech_denoising_plan.model_dump(
                    exclude_none=True, by_alias=True
                )
            )

    def _process_voice_config(
        self, voice_config: Any, speech_rate: Any = None
    ) -> VoiceDecoderConfig:
        """Process voice configuration with field mapping and speech rate."""
        # If speech rate needs to be applied, we need to create a modified copy
        if speech_rate:
            # Convert to dict using aliases, apply speech rate, then recreate the config
            processed_voice = voice_config.model_dump(exclude_none=True, by_alias=True)

            processed_voice = add_voice_speed_if_supported(processed_voice, speech_rate)
            return VoiceDecoderConfig.model_validate(processed_voice)

        # For cases without speech rate, still need to ensure aliases are used
        return VoiceDecoderConfig.model_validate(
            voice_config.model_dump(exclude_none=True, by_alias=True)
        )

    def _apply_extra_config(
        self, assistant_config: dict[str, Any], model_extra: dict[str, Any] | None
    ) -> None:
        """Apply extra configuration fields that are not defined in the model schema."""
        if model_extra:
            # model_extra only contains fields not defined in the schema,
            # so it's safe to apply directly without filtering
            assistant_config.update(model_extra)

    def _build_model_with_system_message(
        self, base_model: Dict[str, Any], system_content: str
    ) -> Dict[str, Any]:
        """Build model configuration with system message."""
        if isinstance(base_model, dict):
            return {
                **base_model,
                "messages": [{"role": "system", "content": system_content}],
            }
        else:
            raise ValueError("Base model must be a dictionary")

    def _set_background_sound(self, assistant_config: dict[str, Any]) -> None:
        """Set background sound from agent voice config."""
        assistant_config["backgroundSound"] = (
            self.agent_config.voice_config.background_noise
        )


class TriageAssistantFactory(BaseAssistantFactory):
    """Factory for creating triage assistants."""

    def create(
        self,
        squad_config: MultilingualSquadConfig,
        account_display_name: str,
        speech_rate: Any,
        api_url: str,
        caller_info: CallerInfo,
    ) -> VAPIAssistant:
        """Create a triage assistant."""
        triage_config = squad_config.triage_assistant

        # Since triage_config is already a VAPIAssistant, we can work with it directly
        # Create a copy with modifications
        assistant_dict = triage_config.model_dump(exclude_none=True, by_alias=True)

        # Use base factory methods for consistent processing
        processed_voice = self._process_voice_config(triage_config.voice, speech_rate)
        assistant_dict["voice"] = processed_voice

        # Update model configuration for triage assistant
        system_content = self._create_system_content(squad_config, account_display_name)

        # If the provider is palona, we want to use our own agent
        if triage_config.model.get("provider", "").lower() == "palona":
            base_model = {
                "provider": "custom-llm",
                "url": f"{api_url}/v1",
                "model": json.dumps(caller_info.model_dump(exclude_none=True)),
            }
            assistant_dict["model"] = self._build_model_with_system_message(
                base_model, system_content
            )
        else:
            assistant_dict["model"] = self._build_model_with_system_message(
                triage_config.model, system_content
            )

        # Set background sound from agent config
        self._set_background_sound(assistant_dict)

        # Use base factory method for background denoising
        self._add_background_denoising(assistant_dict)

        # Apply any extra configuration from the triage config
        self._apply_extra_config(
            assistant_dict, getattr(triage_config, "model_extra", None)
        )

        return VAPIAssistant.model_validate(assistant_dict)

    def _create_system_content(
        self, squad_config: MultilingualSquadConfig, account_display_name: str
    ) -> str:
        """Create system content for triage assistant."""
        agent_name = self.agent_config.persona.name

        # Build language list and transfer rules dynamically
        languages = list(squad_config.language_assistants.keys())

        if not languages:
            raise SquadCreationError("No languages provided in the squad configuration")

        language_list = (
            ", ".join(languages[:-1]) + f", or {languages[-1]}"
            if len(languages) > 1
            else languages[0]
        )

        transfer_rules = []
        for language, config in squad_config.language_assistants.items():
            assistant_name = config.name
            transfer_rules.append(
                f"- For {language.title()} speakers or {language.title()} requests → transfer to {assistant_name}"
            )

        transfer_rules_text = "\n".join(transfer_rules)

        return f"""You are {agent_name}, the initial contact for {account_display_name}.

Your ONLY responsibility is to:
1. Greet the customer warmly
2. Identify their preferred language ({language_list})
3. Transfer them to the appropriate language specialist
4. If the user gives an request in English, transfer them to the English-speaking assistant.

IMPORTANT TRANSFER RULES:
{transfer_rules_text}

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
        # Since language_config is already a VAPIAssistant, we can work with it directly
        # Create a copy with modifications
        assistant_dict = language_config.model_dump(exclude_none=True, by_alias=True)

        # Use base factory methods for consistent processing
        processed_voice = self._process_voice_config(language_config.voice, speech_rate)
        assistant_dict["voice"] = processed_voice

        # Update model configuration for language assistant
        system_content = self._create_system_content(language, account_display_name)
        custom_model = {
            "provider": "custom-llm",
            "url": f"{api_url}/v1",
            "model": json.dumps(caller_info.model_dump(exclude_none=True)),
        }
        assistant_dict["model"] = self._build_model_with_system_message(
            custom_model, system_content
        )

        # Set background sound from agent config
        self._set_background_sound(assistant_dict)

        # Use base factory method for background denoising
        self._add_background_denoising(assistant_dict)

        # Apply any extra configuration from the language config
        self._apply_extra_config(
            assistant_dict, getattr(language_config, "model_extra", None)
        )

        return VAPIAssistant.model_validate(assistant_dict)

    def _create_system_content(self, language: str, account_display_name: str) -> str:
        """Create language-specific system content."""
        agent_name = self.agent_config.persona.name
        agent_description = self.agent_config.persona.description or ""

        templates = {
            "english": f"You are {agent_name}, English customer support representative for {account_display_name}. {agent_description} \n\nKeep responses concise and helpful.",
            "spanish": f"Eres {agent_name}, representante de soporte al cliente en español para {account_display_name}. {agent_description} \n\nMantén las respuestas concisas y útiles.",
            "chinese": f"你是{agent_name}，{account_display_name}的中文客服代表。{agent_description} \n\n保持回答简洁有用。从现在开始必须用中文回复。",
            "general": f"You are {agent_name}, customer support representative for {account_display_name}. {agent_description} \n\nCommunicate in {language.title()} and keep responses concise and helpful.",
        }

        return templates.get(language, templates["general"])


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
            self.squad_config, account_display_name, speech_rate, api_url, caller_info
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
                    assistantName=config.name,
                    message=config.transfer_message,
                    description=config.transfer_description
                    or f"Transfer to {language_name} assistant",
                    transferMode=transfer_mode,
                )
            )

        return destinations


# ============================================================================
# PUBLIC FUNCTIONS
# ============================================================================


def get_squad_model(squad_data: dict[str, Any]) -> dict[str, Any] | None:
    """
    Get the squad model from the squad data.
    """
    # Get language assistant model name from the second member of squad_data.
    # The first member is the triage assistant, and all subsequent members function as language assistants.
    members = squad_data.get("members", [])
    if len(members) < 2:
        logger.error("Squad has fewer than two members; cannot extract language model")
        return None

    language_assistant = members[1]["assistant"]
    model_block = language_assistant.get("model")

    return model_block


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
    1. Language triage assistant (configurable model and transcriber, default to OpenAI GPT-4o and Google transcriber)
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

        # Exclude None values from the squad configuration
        return {"squad": squad_config.model_dump(exclude_none=True, by_alias=True)}

    except SquadCreationError:
        # Re-raise squad creation errors as-is
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating multilingual squad: {str(e)}")
        return {"error": f"Error creating multilingual squad: {str(e)}"}
