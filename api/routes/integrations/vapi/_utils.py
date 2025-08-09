import os
from typing import Any

from fastapi import Request

from db.tables.agents import SpeechRate
from utils.log import logger

from ._constants import (
    CARTESIA_SPEED_MAPPING,
    SPORTSMAN_VOICE_ID,
    VAPI_SECRET_HEADER,
    VAPI_TIMESTAMP_HEADER,
)


def add_voice_speed_if_supported(
    voice_config: dict[str, Any], speech_rate: SpeechRate
) -> dict[str, Any]:
    """
    Add speed parameter to voice config if the provider supports it.
    Currently only supports Cartesia provider.

    Args:
        voice_config: The voice configuration dictionary
        speech_rate: The speech rate enum

    Returns:
        Updated voice config with speed parameter if supported by the provider
    """
    provider = voice_config.get("provider", "").lower()

    if provider == "cartesia":
        voice_config = voice_config.copy()  # Avoid mutating the original dict
        experimental_controls = voice_config.get("experimentalControls", {}).copy()
        experimental_controls["speed"] = CARTESIA_SPEED_MAPPING.get(
            speech_rate, "normal"
        )
        voice_config["experimentalControls"] = experimental_controls
        logger.debug(
            f"Applied Cartesia speed {voice_config['experimentalControls']['speed']} for speech rate {speech_rate}"
        )
        return voice_config  # Return the modified copy

    return voice_config  # Return original for non-Cartesia


def validate_vapi_request(request: Request) -> bool:
    """
    Validate that the request is coming from VAPI by checking its signature.

    Args:
        request: The FastAPI request object

    Returns:
        bool: True if the request is valid, False otherwise

    Note:
        This is a placeholder implementation. You'll need to implement the
        actual validation logic based on VAPI's authentication requirements.
    """
    # Get VAPI secret from environment variables
    vapi_secret = os.environ.get("VAPI_SECRET")

    if not vapi_secret:
        logger.warning("VAPI_SECRET environment variable not set")
        return True  # Allow requests without validation in development

    # Get signature and timestamp from headers
    signature = request.headers.get(VAPI_SECRET_HEADER)
    timestamp = request.headers.get(VAPI_TIMESTAMP_HEADER)

    if not signature or not timestamp:
        logger.warning(
            f"Missing required headers: {VAPI_SECRET_HEADER} or {VAPI_TIMESTAMP_HEADER}"
        )
        return False

    # TODO: Implement signature verification logic here
    # This would typically involve:
    # 1. Creating a signature from the request body and the timestamp
    # 2. Comparing it with the provided signature

    return True


def get_transcriber_and_voice_config(
    agent_config, voice_id: str | None, speech_rate
) -> tuple[dict, dict]:
    """
    Get transcriber and voice configuration for a single assistant.
    Note: Multilingual squad configurations are handled in the _squad.py module.
    """
    # Use transcriber config from agent_config if available
    if agent_config.voice_config.transcriber:
        transcriber_config = agent_config.voice_config.transcriber
        transcriber = {
            "provider": transcriber_config.provider,
            "model": transcriber_config.model,
            "language": transcriber_config.language,
        }

        # Include fallbackPlan if it exists
        if transcriber_config.fallbackPlan:
            transcriber["fallbackPlan"] = [
                {
                    "provider": plan.provider,
                    "model": plan.model,
                    "language": plan.language,
                }
                for plan in transcriber_config.fallbackPlan
            ]
    else:
        # Default single-language setup
        transcriber = {
            "provider": "deepgram",
            "model": "nova-3",
        }

    # Use voice_decoder config from agent_config if available
    if agent_config.voice_config.voice_decoder:
        voice_config = agent_config.voice_config.voice_decoder
        voice = {
            "provider": voice_config.provider,
            "voiceId": voice_config.voice_id or voice_id,
            "model": voice_config.voice_model,
        }

        # Include chunkPlan if it exists
        if voice_config.chunkPlan:
            voice["chunkPlan"] = {
                "enabled": voice_config.chunkPlan.enabled,
                "minCharacters": voice_config.chunkPlan.minCharacters,
            }
            if voice_config.chunkPlan.punctuationBoundaries:
                voice["chunkPlan"][
                    "punctuationBoundaries"
                ] = voice_config.chunkPlan.punctuationBoundaries

        # Include fallbackPlan if it exists
        if voice_config.fallbackPlan:
            voice["fallbackPlan"] = [
                {
                    "provider": plan.provider,
                    "voiceId": plan.voice_id,
                    "model": plan.voice_model,
                }
                for plan in voice_config.fallbackPlan
            ]
    else:
        voice = {
            "provider": "cartesia",
            "voiceId": voice_id or SPORTSMAN_VOICE_ID,
            "model": "sonic",
        }

    # Add speed if provider supports it
    voice = add_voice_speed_if_supported(voice, speech_rate)

    return transcriber, voice
