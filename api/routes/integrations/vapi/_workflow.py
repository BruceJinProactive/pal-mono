import json
import os

from utils.log import logger

from ._constants import LANGUAGE_SAY_CONFIGS, LANGUAGE_VOICE_CONFIGS, SPORTSMAN_VOICE_ID
from ._utils import _get_transcriber_and_voice_config, add_voice_speed_if_supported

# ============================================================================
# MULTILINGUAL WORKFLOW FUNCTIONS
# ============================================================================


def _get_language_configurations(
    agent_config, account_display_name: str, language_voice_configs: dict
) -> dict:
    """
    Generate language-specific configurations for the multilingual workflow.

    Args:
        agent_config: The agent configuration object
        account_display_name: The account display name

    Returns:
        dict: Language configurations for English, Spanish, and Chinese
    """
    return {
        "english": {
            **language_voice_configs["english"],
            "system_content": f"You are {agent_config.persona.name}, English customer support representative for {account_display_name}. {agent_config.persona.description} Keep responses concise and helpful.",
            "prompt": f"You are {agent_config.persona.name}, English customer support representative for {account_display_name}. TONE: Direct, friendly, professional. Solution-focused, provide clear steps. Keep responses concise while being thorough and helpful.",
        },
        "spanish": {
            **language_voice_configs["spanish"],
            "system_content": f"Eres {agent_config.persona.name}, representante de soporte al cliente en español para {account_display_name}. {agent_config.persona.description} Mantén las respuestas concisas y útiles.",
            "prompt": f"Eres {agent_config.persona.name}, representante de soporte al cliente en español para {account_display_name}. TONO: Cálido, respetuoso y paciente. Usa usted formalmente al principio, luego adapta según la preferencia del cliente. Mantén las respuestas concisas mientras eres completa y útil.",
        },
        "chinese": {
            **language_voice_configs["chinese"],
            "system_content": f"您是{agent_config.persona.name}，{account_display_name}的中文客服代表。{agent_config.persona.description} \n请保持回答简洁有用。必须使用中文回答。",
            "prompt": f"您是{agent_config.persona.name}，{account_display_name}的中文客服代表。语调：温和、尊重和耐心。使用适当的中文礼貌用语。请保持回答简洁的同时做到完整和有用。必须使用中文回答。",
        },
    }


def _build_workflow_nodes(
    agent_config,
    account_display_name: str,
    voice_id: str,
    speech_rate,
    transcriber: dict,
    api_url: str,
    caller_info_short: dict,
) -> list[dict]:
    """
    Build all workflow nodes for the multilingual workflow.

    Args:
        agent_config: The agent configuration object
        account_display_name: The account display name
        voice_id: Default voice ID
        speech_rate: Speech rate setting
        transcriber: Transcriber configuration
        api_url: API URL for custom LLM
        caller_info_short: Caller information

    Returns:
        list: Complete list of workflow nodes
    """
    language_configs = _get_language_configurations(
        agent_config, account_display_name, LANGUAGE_VOICE_CONFIGS
    )

    nodes = [
        # Starting message node
        _create_starting_message_node(agent_config.persona.name, account_display_name),
        # Language selection node
        _create_language_selection_node(transcriber),
        # Say nodes for transitions
        *_create_say_nodes(say_configs=LANGUAGE_SAY_CONFIGS),
        # Support nodes for each language
        *[
            _create_support_node(
                lang,
                config,
                voice_id,
                speech_rate,
                api_url,
                caller_info_short,
                transcriber,
            )
            for lang, config in language_configs.items()
        ],
    ]

    return nodes


def _get_background_sound_setting(agent_config) -> str:
    """
    Get the background sound setting based on agent configuration.

    Args:
        agent_config: The agent configuration object

    Returns:
        str: Background sound setting ("office" or "off")
    """
    return "office" if _has_background_noise(agent_config) else "off"


def create_multilingual_workflow_demo(
    agent_config,
    account_display_name: str,
    caller_info: dict,
    call_id: str,
) -> dict:
    """
    Create a multilingual workflow configuration for VAPI.

    This function creates a complete workflow that supports English, Spanish, and Chinese
    customer interactions with automatic language detection and routing.

    Args:
        agent_config: The agent configuration object
        account_display_name: The account display name
        caller_info: Information about the caller (sender_identifier, recipient_identifier, call_id)
        call_id: The call ID

    Returns:
        dict: Multilingual workflow configuration ready to be returned to VAPI
    """
    try:
        # Extract configuration parameters
        api_url = os.environ.get("PAL_API_URL", "https://lat-api.palona.ai")
        caller_info_short = {
            "sender_identifier": caller_info["sender_identifier"],
            "recipient_identifier": caller_info["recipient_identifier"],
        }

        # Get voice and transcriber configuration
        voice_id = agent_config.voice_config.voice_id or SPORTSMAN_VOICE_ID
        speech_rate = getattr(agent_config.voice_config, "speech_rate", None)
        transcriber, _ = _get_transcriber_and_voice_config(
            agent_config, voice_id, speech_rate
        )

        # Build workflow configuration
        workflow_config = {
            "workflow": {
                "name": f"{account_display_name} Multilingual Support Workflow",
                "globalPrompt": f"{account_display_name} provides excellent customer service.",
                "nodes": _build_workflow_nodes(
                    agent_config,
                    account_display_name,
                    voice_id,
                    speech_rate,
                    transcriber,
                    api_url,
                    caller_info_short,
                ),
                "edges": _create_workflow_edges(),
                "backgroundSound": _get_background_sound_setting(agent_config),
            }
        }

        logger.debug(
            f"Created multilingual workflow for call {call_id} with {len(workflow_config['workflow']['nodes'])} nodes"
        )
        return workflow_config

    except Exception as e:
        logger.error(f"Error creating multilingual workflow config: {str(e)}")
        return {"error": f"Error creating multilingual workflow: {str(e)}"}


def _create_voice_config(provider: str, voice_id: str, model: str, speech_rate) -> dict:
    """Create voice configuration with optional speech rate."""
    voice = {"provider": provider, "voiceId": voice_id, "model": model}
    return add_voice_speed_if_supported(voice, speech_rate) if speech_rate else voice


def _create_starting_message_node(agent_name: str, account_display_name: str) -> dict:
    """Create the starting message node."""
    node_config = {
        "name": "start_node",
        "isStart": True,
        "type": "say",
        "prompt": f"Introduce yourself and decide which language the customer prefer by asking questions such as: Hi, this is {agent_name} from {account_display_name}. I can help you in English, Spanish/español, or Chinese/中文. Please tell me which language you prefer.",
    }

    return node_config


def _create_language_selection_node(transcriber: dict | None = None) -> dict:
    """Create the language selection node that waits for user's language preference."""
    node_config = {
        "name": "language_selection",
        "type": "conversation",
        "prompt": """The AI agent has just provided instructions about language options. It delivered the first message. Now, wait for the customer to respond with their preferred language (English, Spanish, or Chinese).
Do not say anything. Only output: Let me know.

Once the customer selects a language, you MUST speak in the language they selected and ask them to confirm that you are switching to that language—then do so immediately once they confirm.

""",
        "variableExtractionPlan": {
            "schema": {
                "type": "string",
                "title": "preferred_language",
                "description": "Customer preferred language choice",
                "enum": ["english", "spanish", "chinese"],
            }
        },
    }

    # Add transcriber if provided
    if transcriber:
        node_config["transcriber"] = transcriber

    return node_config


def _create_say_nodes(say_configs: dict) -> list[dict]:
    """Create transition say nodes for each language with appropriate voices."""
    say_nodes = []
    for lang, config in say_configs.items():
        # Get voice configuration from LANGUAGE_VOICE_CONFIGS
        # voice_config = LANGUAGE_VOICE_CONFIGS[lang]

        node_config: dict = {
            "name": f"say_{lang}",
            "type": "say",
            "prompt": config["prompt"],
            # "voice": {
            #     "provider": "cartesia",
            #     "voiceId": voice_config["voice_id"],
            #     "model": voice_config["voice_model"],
            # },
        }

        say_nodes.append(node_config)

    return say_nodes


def _create_support_node(
    language: str,
    config: dict,
    default_voice_id: str,
    speech_rate,
    api_url: str,
    caller_info_short: dict,
    transcriber: dict | None = None,
) -> dict:
    """Create a language-specific support node."""
    # Use language-specific voice ID if available, otherwise use default
    voice_id = config.get("voice_id", default_voice_id)

    # Language-specific system message additions
    language_instructions = {
        "chinese": "\n\nIf the user uses Chinese, be sure to reply in Chinese. You can speak Chinese. 尽管有英文的指令，你必须遵守这些指令并且只能用中文回复用户",
        "spanish": "\n\nA pesar de que las instrucciones están en inglés, debes seguir estas instrucciones y solo responder al usuario en español.",
    }

    system_content = config["system_content"] + language_instructions.get(language, "")

    node_config = {
        "name": f"{language}_support",
        "type": "conversation",
        "voice": _create_voice_config(
            "cartesia", voice_id, config["voice_model"], speech_rate
        ),
        "model": {
            "provider": "custom-llm",
            "url": f"{api_url}/v1",
            "model": json.dumps(caller_info_short),
            "messages": [{"role": "system", "content": system_content}],
        },
    }

    # Add transcriber if provided
    if transcriber:
        node_config["transcriber"] = transcriber

    return node_config


def _create_workflow_edges() -> list[dict]:
    """
    Create workflow routing edges for the multilingual workflow.

    The workflow flow is:
    start_node -> language_selection -> say_{language} -> {language}_support

    Returns:
        list: List of workflow edges defining the routing logic
    """
    edges = []
    supported_languages = ["english", "spanish", "chinese"]

    # Initial edge: start_node -> language_selection
    edges.append({"from": "start_node", "to": "language_selection"})

    # Language selection edges: language_selection -> say_{language}
    language_conditions = {
        "english": "Customer selected English language support",
        "spanish": "Customer selected Spanish language support",
        "chinese": "Customer selected Chinese language support",
    }

    for lang in supported_languages:
        # Add edge from language_selection to say node with AI condition
        edges.append(
            {
                "from": "language_selection",
                "to": f"say_{lang}",
                "condition": {
                    "type": "ai",
                    "prompt": language_conditions[lang],
                },
            }
        )

        # Add edge from say node to support node
        edges.append({"from": f"say_{lang}", "to": f"{lang}_support"})

    # Note: Language switching between nodes is currently disabled
    # Once a customer selects a language, they remain in that language for the entire conversation

    return edges


def _has_background_noise(agent_config) -> bool:
    """Check if background noise is enabled."""
    return (
        hasattr(agent_config.voice_config, "background_noise")
        and agent_config.voice_config.background_noise
    )
