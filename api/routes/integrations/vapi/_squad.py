import json
import os
from typing import Any, Dict, List, Optional

from utils.log import logger

from ._constants import (
    CHINESE_ASSISTANT_NAME,
    DEFAULT_API_URL,
    DEFAULT_SILENCE_TIMEOUT,
    ENGLISH_ASSISTANT_NAME,
    FIRST_MESSAGES,
    LANGUAGE_VOICE_CONFIGS,
    SPANISH_ASSISTANT_NAME,
    TRANSFER_MODE,
    TRIAGE_ASSISTANT_NAME,
)
from ._utils import add_voice_speed_if_supported
from .schema import (
    AssistantDestination,
    CallerInfo,
    SquadConfig,
    SquadMember,
    VAPIAssistant,
)

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
            # Use nova-3 for multi-language and english
            if language == "multi" or language == "en-US" or language == "en":
                config["language"] = language
            else:
                config["language"] = language
                config["model"] = "nova-2"

        else:
            config["language"] = "en-US"
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
        "chinese": f"你是{agent_name}，{account_name}的中文客服代表。{agent_description} \n\n保持回答简洁有用。从现在开始必须用中文回复， 否则用户听不懂。",
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
    background_sound: str,
    speech_rate: Any,
) -> VAPIAssistant:
    """Create the language triage assistant for initial language detection."""

    transcriber = _create_transcriber_config("google")
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

    first_message = f"Hello! This is {agent_config.persona.name} from {account_display_name}. I can help you in English, español, or 中文. Please let me know which language you prefer, and I'll connect you with the right folk."

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
    transcriber: Dict[str, Any],
    first_message: str,
    background_sound: str,
    speech_rate: Any,
    caller_info: CallerInfo,
    api_url: str,
    agent_config: Any,
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
            message="Got it!",
            description="Transfer to English-speaking assistant when customer prefers English or uses English language.",
            transferMode=TRANSFER_MODE,
        ),
        AssistantDestination(
            assistantName=SPANISH_ASSISTANT_NAME,
            message="Perfecto, te conecto con alguien que te puede ayudar en español. Un momentito.",
            description="Transfer to Spanish-speaking assistant when customer prefers Spanish, says 'español', or uses Spanish language.",
            transferMode=TRANSFER_MODE,
        ),
        AssistantDestination(
            assistantName=CHINESE_ASSISTANT_NAME,
            message="好的，正在为您安排中文服务，请稍候片刻。",
            description="Transfer to Chinese-speaking assistant when customer prefers Chinese, says '中文', uses Chinese characters, or indicates Chinese language preference.",
            transferMode=TRANSFER_MODE,
        ),
    ]


# ============================================================================
# MAIN SQUAD CREATION
# ============================================================================


def _create_all_assistants(
    agent_config: Any,
    account_display_name: str,
    background_sound: str,
    speech_rate: Any,
    caller_info: CallerInfo,
    api_url: str,
) -> Dict[str, VAPIAssistant]:
    """Create all four assistants for the squad."""
    language_configs = _get_language_configurations(agent_config, account_display_name)

    assistants = {}

    # Create triage assistant
    assistants["triage"] = _create_triage_assistant(
        agent_config, account_display_name, background_sound, speech_rate
    )

    # Create language assistants with cleaner config
    language_assistant_configs = [
        ("english", ENGLISH_ASSISTANT_NAME, "deepgram", "en-US"),
        ("spanish", SPANISH_ASSISTANT_NAME, "deepgram", "es"),
        ("chinese", CHINESE_ASSISTANT_NAME, "deepgram", "zh-CN"),
    ]

    for (
        lang_key,
        assistant_name,
        transcriber_type,
        transcriber_lang,
    ) in language_assistant_configs:
        transcriber = _create_transcriber_config(transcriber_type, transcriber_lang)

        assistants[lang_key] = _create_language_assistant(
            name=assistant_name,
            language_config=language_configs[lang_key],
            transcriber=transcriber,
            first_message=FIRST_MESSAGES[lang_key],
            background_sound=background_sound,
            speech_rate=speech_rate,
            caller_info=caller_info,
            api_url=api_url,
            agent_config=agent_config,
        )

    return assistants


def create_multilingual_squad_demo(
    agent_config: Any,
    account_display_name: str,
    caller_info: Dict[str, Any],
    call_id: str,
) -> Dict[str, Any]:
    """
    Create a multilingual squad configuration with 4 assistants:
    1. Language triage assistant (OpenAI GPT-4o, Google transcriber)
    2. English assistant (Deepgram transcriber)
    3. Spanish assistant (Deepgram transcriber)
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
        # Extract configuration
        api_url = os.environ.get("PAL_API_URL", DEFAULT_API_URL)
        speech_rate = getattr(agent_config.voice_config, "speech_rate", None)
        background_sound = _get_background_sound(agent_config)

        # Structure caller info
        structured_caller_info = CallerInfo(
            sender_identifier=caller_info["sender_identifier"],
            recipient_identifier=caller_info["recipient_identifier"],
            call_id=call_id,
        )

        # Create assistants and destinations
        assistants = _create_all_assistants(
            agent_config,
            account_display_name,
            background_sound,
            speech_rate,
            structured_caller_info,
            api_url,
        )
        triage_destinations = _create_triage_destinations()

        # Build squad configuration
        squad_config = SquadConfig(
            name=f"{account_display_name} Multilingual Support Squad",
            members=[
                SquadMember(
                    assistant=assistants["triage"],
                    assistantDestinations=triage_destinations,
                ),
                SquadMember(assistant=assistants["english"]),
                SquadMember(assistant=assistants["spanish"]),
                SquadMember(assistant=assistants["chinese"]),
            ],
        )

        return {"squad": squad_config.model_dump()}

    except Exception as e:
        logger.error(f"Error creating multilingual squad config: {str(e)}")
        return {"error": f"Error creating multilingual squad: {str(e)}"}
