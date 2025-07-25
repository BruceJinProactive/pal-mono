import json
import os
from typing import Any, Dict, List, Optional

from utils.log import logger

from ._constants import FIRST_MESSAGES, LANGUAGE_VOICE_CONFIGS
from ._utils import add_voice_speed_if_supported
from .schema import (
    AssistantDestination,
    CallerInfo,
    SquadConfig,
    SquadMember,
    VAPIAssistant,
)

# ============================================================================
# CONSTANTS
# ============================================================================

DEFAULT_SILENCE_TIMEOUT = 60
DEFAULT_API_URL = "https://lat-api.palona.ai"

# Transfer modes
TRANSFER_MODE = "swap-system-message-in-history"

# Assistant names
TRIAGE_ASSISTANT_NAME = "language_triage_assistant"
ENGLISH_ASSISTANT_NAME = "english_assistant"
SPANISH_ASSISTANT_NAME = "spanish_assistant"
CHINESE_ASSISTANT_NAME = "chinese_assistant"


# ============================================================================
# TRANSCRIBER CONFIGURATION
# ============================================================================


def _create_transcriber_config(
    transcriber_type: str, language: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create transcriber configuration based on type and language.

    Args:
        transcriber_type: Either "google" or "deepgram"
        language: Language code for deepgram (e.g., "en", "es") or language name for google (e.g., "English", "Spanish")

    Returns:
        Transcriber configuration dictionary

    Raises:
        ValueError: If transcriber_type is not supported
    """
    if transcriber_type == "google":
        config = {
            "provider": "google",
            "model": "gemini-2.5-flash",
            "language": language if language else "Multilingual",
        }
        return config
    elif transcriber_type == "deepgram":
        config = {
            "provider": "deepgram",
            "model": "nova-3",
        }
        if language:
            config["language"] = language
        return config
    else:
        raise ValueError(f"Unsupported transcriber type: {transcriber_type}")


# ============================================================================
# LANGUAGE CONFIGURATION
# ============================================================================


def _create_language_system_content(
    agent_name: str, account_name: str, agent_description: str, language: str
) -> str:
    """Create language-specific system content without switching instructions."""
    templates = {
        "english": f"You are {agent_name}, English customer support representative for {account_name}. {agent_description} Keep responses concise and helpful.",
        "spanish": f"Eres {agent_name}, representante de soporte al cliente en español para {account_name}. {agent_description} Mantén las respuestas concisas y útiles.",
        "chinese": f"您是{agent_name}，{account_name}的中文客服代表。{agent_description} \n请保持回答简洁有用。必须使用中文回答。",
    }
    return templates.get(language, templates["english"])


def _get_language_configurations(
    agent_config: Any, account_display_name: str
) -> Dict[str, Dict[str, Any]]:
    """Generate clean language-specific configurations without transfer instructions."""
    return {
        "english": {
            **LANGUAGE_VOICE_CONFIGS["english"],
            "system_content": _create_language_system_content(
                agent_config.persona.name,
                account_display_name,
                agent_config.persona.description,
                "english",
            ),
        },
        "spanish": {
            **LANGUAGE_VOICE_CONFIGS["spanish"],
            "system_content": _create_language_system_content(
                agent_config.persona.name,
                account_display_name,
                agent_config.persona.description,
                "spanish",
            ),
        },
        "chinese": {
            **LANGUAGE_VOICE_CONFIGS["chinese"],
            "system_content": _create_language_system_content(
                agent_config.persona.name,
                account_display_name,
                agent_config.persona.description,
                "chinese",
            ),
        },
    }


# ============================================================================
# VOICE AND ASSISTANT CONFIGURATION
# ============================================================================


def _create_voice_config(
    language_config: Dict[str, Any], speech_rate: Any
) -> Dict[str, Any]:
    """Create voice configuration with optional speech rate."""
    voice_config = {
        "provider": "cartesia",
        "voiceId": language_config["voice_id"],
        "model": language_config["voice_model"],
    }

    if speech_rate:
        voice_config = add_voice_speed_if_supported(voice_config, speech_rate)

    return voice_config


def _add_background_denoising(
    assistant_config: Dict[str, Any], agent_config: Any
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


def _get_background_sound(agent_config: Any) -> str:
    """Determine background sound setting."""
    return (
        "office"
        if hasattr(agent_config.voice_config, "background_noise")
        and agent_config.voice_config.background_noise
        else "off"
    )


def _create_base_assistant_config(
    name: str,
    first_message: str,
    transcriber: Dict[str, Any],
    voice_config: Dict[str, Any],
    background_sound: str,
    system_content: str,
    model_config: Dict[str, Any],
    agent_config: Any,
) -> Dict[str, Any]:
    """Create base assistant configuration with common settings."""
    config = {
        "name": name,
        "firstMessage": first_message,
        "transcriber": transcriber,
        "voice": voice_config,
        "backgroundSound": background_sound,
        "silenceTimeoutSeconds": DEFAULT_SILENCE_TIMEOUT,
        "backgroundDenoisingEnabled": True,
        "model": {
            **model_config,
            "messages": [{"role": "system", "content": system_content}],
        },
    }

    _add_background_denoising(config, agent_config)
    return config


# ============================================================================
# ASSISTANT CREATION
# ============================================================================


def _create_triage_assistant(
    agent_config: Any,
    account_display_name: str,
    transcriber: Dict[str, Any],
    background_sound: str,
    speech_rate: Any,
) -> VAPIAssistant:
    """Create the language triage assistant for initial language detection."""

    voice_config = _create_voice_config(LANGUAGE_VOICE_CONFIGS["english"], speech_rate)

    system_content = f"""You are {agent_config.persona.name}, the initial contact for {account_display_name}. 

Your ONLY responsibility is to:
1. Greet the customer warmly
2. Identify their preferred language (English, Spanish, or Chinese)
3. Transfer them to the appropriate language specialist

IMPORTANT TRANSFER RULES:
- For English speakers or English requests → transfer to {ENGLISH_ASSISTANT_NAME}
- For Spanish speakers, "español", or Spanish requests → transfer to {SPANISH_ASSISTANT_NAME}  
- For Chinese speakers, "中文", Chinese characters, or Chinese requests → transfer to {CHINESE_ASSISTANT_NAME}

DO NOT attempt to help with their actual request - only identify language preference and transfer immediately."""

    first_message = f"Hello! This is {agent_config.persona.name} from {account_display_name}. I can help you in English, español, or Chinese/中文. Please let me know which language you prefer, and I'll connect you with the right specialist."

    model_config = {
        "provider": "openai",
        "model": "gpt-4o",
    }

    config = _create_base_assistant_config(
        name=TRIAGE_ASSISTANT_NAME,
        first_message=first_message,
        transcriber=transcriber,
        voice_config=voice_config,
        background_sound=background_sound,
        system_content=system_content,
        model_config=model_config,
        agent_config=agent_config,
    )

    return VAPIAssistant(**config)


def _create_language_assistant(
    name: str,
    language_config: Dict[str, Any],
    agent_config: Any,
    transcriber: Dict[str, Any],
    background_sound: str,
    caller_info: CallerInfo,
    api_url: str,
    speech_rate: Any,
    first_message: str,
) -> VAPIAssistant:
    """Create a language-specific support assistant."""

    voice_config = _create_voice_config(language_config, speech_rate)

    model_config = {
        "provider": "custom-llm",
        "url": f"{api_url}/v1",
        "model": json.dumps(caller_info.__dict__),
    }

    config = _create_base_assistant_config(
        name=name,
        first_message=first_message,
        transcriber=transcriber,
        voice_config=voice_config,
        background_sound=background_sound,
        system_content=language_config["system_content"],
        model_config=model_config,
        agent_config=agent_config,
    )

    return VAPIAssistant(**config)


# ============================================================================
# DESTINATION CREATION
# ============================================================================


def _create_triage_destinations() -> List[AssistantDestination]:
    """Create transfer destinations for the triage assistant."""
    return [
        AssistantDestination(
            assistantName=ENGLISH_ASSISTANT_NAME,
            message="Perfect! Let me connect you with our English specialist.",
            description="Transfer to English-speaking assistant when customer prefers English or uses English language.",
            transferMode=TRANSFER_MODE,
        ),
        AssistantDestination(
            assistantName=SPANISH_ASSISTANT_NAME,
            message="¡Perfecto! Te conecto con nuestro especialista en español.",
            description="Transfer to Spanish-speaking assistant when customer prefers Spanish, says 'español', or uses Spanish language.",
            transferMode=TRANSFER_MODE,
        ),
        AssistantDestination(
            assistantName=CHINESE_ASSISTANT_NAME,
            message="好的！让我为您连接到我们的中文专家。",
            description="Transfer to Chinese-speaking assistant when customer prefers Chinese, says '中文', uses Chinese characters, or indicates Chinese language preference.",
            transferMode=TRANSFER_MODE,
        ),
    ]


# ============================================================================
# MAIN SQUAD CREATION
# ============================================================================


def _create_assistants(
    agent_config: Any,
    account_display_name: str,
    background_sound: str,
    speech_rate: Any,
    caller_info: CallerInfo,
    api_url: str,
    language_configs: Dict[str, Dict[str, Any]],
) -> tuple[VAPIAssistant, VAPIAssistant, VAPIAssistant, VAPIAssistant]:
    """Create all four assistants for the squad."""

    # Create transcriber configurations
    triage_transcriber = _create_transcriber_config("google")
    english_transcriber = _create_transcriber_config("google", "English")
    spanish_transcriber = _create_transcriber_config("google", "Spanish")
    chinese_transcriber = _create_transcriber_config("google", "Chinese")

    # Create triage assistant
    triage_assistant = _create_triage_assistant(
        agent_config=agent_config,
        account_display_name=account_display_name,
        transcriber=triage_transcriber,
        background_sound=background_sound,
        speech_rate=speech_rate,
    )

    # Create language assistants
    english_assistant = _create_language_assistant(
        name=ENGLISH_ASSISTANT_NAME,
        language_config=language_configs["english"],
        agent_config=agent_config,
        transcriber=english_transcriber,
        background_sound=background_sound,
        caller_info=caller_info,
        api_url=api_url,
        speech_rate=speech_rate,
        first_message=FIRST_MESSAGES["english"](
            agent_config.persona.name, account_display_name
        ),
    )

    spanish_assistant = _create_language_assistant(
        name=SPANISH_ASSISTANT_NAME,
        language_config=language_configs["spanish"],
        agent_config=agent_config,
        transcriber=spanish_transcriber,
        background_sound=background_sound,
        caller_info=caller_info,
        api_url=api_url,
        speech_rate=speech_rate,
        first_message=FIRST_MESSAGES["spanish"](
            agent_config.persona.name, account_display_name
        ),
    )

    chinese_assistant = _create_language_assistant(
        name=CHINESE_ASSISTANT_NAME,
        language_config=language_configs["chinese"],
        agent_config=agent_config,
        transcriber=chinese_transcriber,
        background_sound=background_sound,
        caller_info=caller_info,
        api_url=api_url,
        speech_rate=speech_rate,
        first_message=FIRST_MESSAGES["chinese"](
            agent_config.persona.name, account_display_name
        ),
    )

    return triage_assistant, english_assistant, spanish_assistant, chinese_assistant


def create_multilingual_squad_demo(
    agent_config: Any,
    account_display_name: str,
    caller_info: Dict[str, Any],
    call_id: str,
) -> Dict[str, Any]:
    """
    Create a multilingual squad configuration with 4 assistants:
    1. Language triage assistant (OpenAI GPT-4o, Google transcriber, Sportsman voice)
    2. English assistant (Deepgram transcriber with language "en")
    3. Spanish assistant (Deepgram transcriber with language "es")
    4. Chinese assistant (Google transcriber)

    Args:
        agent_config: The agent configuration object
        account_display_name: The account display name
        caller_info: Information about the caller
        call_id: The call ID

    Returns:
        Squad configuration ready to be returned to VAPI
    """
    try:
        # Extract and validate configuration
        api_url = os.environ.get("PAL_API_URL", DEFAULT_API_URL)
        speech_rate = getattr(agent_config.voice_config, "speech_rate", None)
        background_sound = _get_background_sound(agent_config)

        # Structure caller info
        structured_caller_info = CallerInfo(
            sender_identifier=caller_info["sender_identifier"],
            recipient_identifier=caller_info["recipient_identifier"],
            call_id=call_id,
        )

        # Get language configurations
        language_configs = _get_language_configurations(
            agent_config, account_display_name
        )

        # Create all assistants
        triage_assistant, english_assistant, spanish_assistant, chinese_assistant = (
            _create_assistants(
                agent_config=agent_config,
                account_display_name=account_display_name,
                background_sound=background_sound,
                speech_rate=speech_rate,
                caller_info=structured_caller_info,
                api_url=api_url,
                language_configs=language_configs,
            )
        )

        # Create triage destinations
        triage_destinations = _create_triage_destinations()

        # Build squad configuration
        squad_config = SquadConfig(
            name=f"{account_display_name} Multilingual Support Squad",
            members=[
                SquadMember(
                    assistant=triage_assistant,
                    assistantDestinations=triage_destinations,
                ),
                SquadMember(assistant=english_assistant),
                SquadMember(assistant=spanish_assistant),
                SquadMember(assistant=chinese_assistant),
            ],
        )

        return {"squad": squad_config.model_dump()}

    except Exception as e:
        logger.error(f"Error creating multilingual squad config: {str(e)}")
        return {"error": f"Error creating multilingual squad: {str(e)}"}
