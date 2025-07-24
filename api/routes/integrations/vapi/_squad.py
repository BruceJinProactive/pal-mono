import json
import os
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, model_validator

from utils.log import logger

from ._constants import FIRST_MESSAGES, LANGUAGE_VOICE_CONFIGS, SPORTSMAN_VOICE_ID
from ._utils import _get_transcriber_and_voice_config, add_voice_speed_if_supported
from ._workflow import _get_language_configurations


class VAPIAssistant(BaseModel):
    name: str
    firstMessage: str
    transcriber: dict
    model: dict | str
    voice: dict
    backgroundSound: str
    silenceTimeoutSeconds: int = 60
    backgroundDenoisingEnabled: bool = True

    # Allow not defined fields to be added to the assistant config
    model_config = ConfigDict(extra="allow")


class AssistantDestination(BaseModel):
    assistantName: str
    message: (
        str  # This is spoken to the customer before connecting them to the destination.
    )
    description: str  # This is the description of the destination, used by the AI to choose when and how to transfer the call.
    transferMode: Literal["rolling-history", "swap-system-message-in-history"]
    type: Literal["assistant"] = "assistant"


class SquadMember(BaseModel):
    assistantId: Optional[str] = None  # For existing assistants
    assistant: Optional[VAPIAssistant] = None  # For transient assistants
    assistantDestinations: Optional[list[AssistantDestination]] = (
        None  # Transfer destinations for this member
    )

    @model_validator(mode="after")
    def validate_assistant_or_assistant_id(self):
        if self.assistant is None and self.assistantId is None:
            raise ValueError("Either assistant or assistantId must be provided")
        return self


class SquadConfig(BaseModel):
    name: str
    members: list[
        SquadMember
    ]  # This is the list of squad members that make up the squad.


def _create_voice_config(language_config: dict, speech_rate) -> dict:
    """Create voice configuration with optional speech rate."""
    voice_config = {
        "provider": "cartesia",
        "voiceId": language_config["voice_id"],
        "model": language_config["voice_model"],
    }

    if speech_rate:
        voice_config = add_voice_speed_if_supported(voice_config, speech_rate)

    return voice_config


def _add_background_denoising_if_available(
    assistant_config: dict, agent_config
) -> None:
    """Add background speech denoising configuration if available."""
    if (
        hasattr(agent_config.voice_config, "background_speech_denoising_plan")
        and agent_config.voice_config.background_speech_denoising_plan
    ):
        assistant_config["backgroundSpeechDenoisingPlan"] = (
            agent_config.voice_config.background_speech_denoising_plan.model_dump(
                exclude_none=True
            )
        )


def _create_assistant_config(
    first_message: str,
    transcriber: dict,
    system_content: str,
    voice_config: dict,
    background_sound: str,
    caller_info: dict,
    api_url: str,
) -> dict:
    """Create base assistant configuration."""
    return {
        "firstMessage": first_message,
        "transcriber": transcriber,
        "model": {
            "provider": "custom-llm",
            "url": f"{api_url}/v1",
            "model": json.dumps(caller_info),
            "messages": [{"role": "system", "content": system_content}],
        },
        "voice": voice_config,
        "backgroundSound": background_sound,
        "silenceTimeoutSeconds": 60,
        "backgroundDenoisingEnabled": True,
    }


def _create_language_assistant(
    name: str,
    language: str,
    language_config: dict,
    agent_config,
    transcriber: dict,
    background_sound: str,
    caller_info: dict,
    api_url: str,
    speech_rate,
    first_message: str,
) -> VAPIAssistant:
    """Create a complete language-specific assistant."""
    # Create voice configuration
    voice_config = _create_voice_config(language_config, speech_rate)

    # Create base assistant configuration
    assistant_config = _create_assistant_config(
        first_message=first_message,
        transcriber=transcriber,
        system_content=language_config["system_content"],
        voice_config=voice_config,
        background_sound=background_sound,
        caller_info=caller_info,
        api_url=api_url,
    )

    # Add background speech denoising if available
    _add_background_denoising_if_available(assistant_config, agent_config)

    # Add name
    assistant_config["name"] = name

    return VAPIAssistant(**assistant_config)


def create_multilingual_squad_demo(
    agent_config,
    account_display_name: str,
    caller_info: dict,
    call_id: str,
) -> dict:
    """
    Create a multilingual squad configuration for VAPI.

    This function creates a squad with multiple assistants - one for each supported
    language (English, Spanish, Chinese) with appropriate voice configurations.

    Args:
        agent_config: The agent configuration object
        account_display_name: The account display name
        caller_info: Information about the caller (sender_identifier, recipient_identifier, call_id)
        call_id: The call ID

    Returns:
        dict: Squad configuration ready to be returned to VAPI
    """
    try:
        # Extract configuration parameters
        api_url = os.environ.get("PAL_API_URL", "https://lat-api.palona.ai")
        caller_info = {
            "sender_identifier": caller_info["sender_identifier"],
            "recipient_identifier": caller_info["recipient_identifier"],
            "call_id": call_id,
        }

        # Get voice and transcriber configuration
        voice_id = agent_config.voice_config.voice_id or SPORTSMAN_VOICE_ID
        speech_rate = getattr(agent_config.voice_config, "speech_rate", None)
        transcriber, _ = _get_transcriber_and_voice_config(
            agent_config, voice_id, speech_rate
        )

        # Get background sound setting
        if (
            hasattr(agent_config.voice_config, "background_noise")
            and agent_config.voice_config.background_noise
        ):
            background_sound = "office"
        else:
            background_sound = "off"

        # Get language-specific configurations
        language_configs = _get_language_configurations(
            agent_config, account_display_name, LANGUAGE_VOICE_CONFIGS
        )

        # Create multilingual greeting for the main assistant
        multilingual_greeting = f"Hello! This is {agent_config.persona.name} from {account_display_name}. I can help you in English, español, or Chinese. How can I assist you today?"

        # Create assistant destinations for each language assistant

        # For English assistant: can transfer to Spanish and Chinese
        english_destinations = [
            AssistantDestination(
                assistantName="spanish_assistant",
                message="¡Perfecto! Te conecto con nuestro soporte en español.",
                description="Transfer to Spanish-speaking assistant when the customer explicitly requests help in Spanish, says 'español', uses Spanish phrases, or indicates they prefer Spanish language support.",
                transferMode="swap-system-message-in-history",
            ),
            AssistantDestination(
                assistantName="chinese_assistant",
                message="好的！让我为您连接到我们的中文客服。",
                description="Transfer to Chinese-speaking assistant when the customer explicitly requests help in Chinese, says '中文', uses Chinese characters/phrases, or indicates they prefer Chinese language support.",
                transferMode="swap-system-message-in-history",
            ),
        ]

        # For Spanish assistant: can transfer to English and Chinese
        spanish_destinations = [
            AssistantDestination(
                assistantName="english_assistant",
                message="Perfect! I'll connect you with our English support.",
                description="Transfer to English-speaking assistant when the customer explicitly requests help in English, switches to English, or indicates they prefer English language support.",
                transferMode="swap-system-message-in-history",
            ),
            AssistantDestination(
                assistantName="chinese_assistant",
                message="好的！让我为您连接到我们的中文客服。",
                description="Transfer to Chinese-speaking assistant when the customer explicitly requests help in Chinese, says '中文', uses Chinese characters/phrases, or indicates they prefer Chinese language support.",
                transferMode="swap-system-message-in-history",
            ),
        ]

        # For Chinese assistant: can transfer to English and Spanish
        chinese_destinations = [
            AssistantDestination(
                assistantName="english_assistant",
                message="Perfect! I'll connect you with our English support.",
                description="Transfer to English-speaking assistant when the customer explicitly requests help in English, switches to English, or indicates they prefer English language support.",
                transferMode="swap-system-message-in-history",
            ),
            AssistantDestination(
                assistantName="spanish_assistant",
                message="¡Perfecto! Te conecto con nuestro soporte en español.",
                description="Transfer to Spanish-speaking assistant when the customer explicitly requests help in Spanish, says 'español', uses Spanish phrases, or indicates they prefer Spanish language support.",
                transferMode="swap-system-message-in-history",
            ),
        ]

        # Create assistants using helper functions
        english_assistant = _create_language_assistant(
            name="english_assistant",
            language="english",
            language_config=language_configs["english"],
            agent_config=agent_config,
            transcriber=transcriber,
            background_sound=background_sound,
            caller_info=caller_info,
            api_url=api_url,
            speech_rate=speech_rate,
            first_message=multilingual_greeting,
        )

        spanish_assistant = _create_language_assistant(
            name="spanish_assistant",
            language="spanish",
            language_config=language_configs["spanish"],
            agent_config=agent_config,
            transcriber=transcriber,
            background_sound=background_sound,
            caller_info=caller_info,
            api_url=api_url,
            speech_rate=speech_rate,
            first_message=FIRST_MESSAGES["spanish"](
                agent_config.persona.name, account_display_name
            ),
        )

        chinese_assistant = _create_language_assistant(
            name="chinese_assistant",
            language="chinese",
            language_config=language_configs["chinese"],
            agent_config=agent_config,
            transcriber=transcriber,
            background_sound=background_sound,
            caller_info=caller_info,
            api_url=api_url,
            speech_rate=speech_rate,
            first_message=FIRST_MESSAGES["chinese"](
                agent_config.persona.name, account_display_name
            ),
        )

        # Create squad configuration
        squad_config = SquadConfig(
            name=f"{account_display_name} Multilingual Support Squad",
            members=[
                SquadMember(
                    assistant=english_assistant,
                    assistantDestinations=english_destinations,
                ),
                SquadMember(
                    assistant=spanish_assistant,
                    assistantDestinations=spanish_destinations,
                ),
                SquadMember(
                    assistant=chinese_assistant,
                    assistantDestinations=chinese_destinations,
                ),
            ],
        )

        return {"squad": squad_config.model_dump()}

    except Exception as e:
        logger.error(f"Error creating multilingual squad config: {str(e)}")
        return {"error": f"Error creating multilingual squad: {str(e)}"}
