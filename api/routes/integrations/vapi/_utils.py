import os
from typing import Any, Dict

from fastapi import Request

from db.tables.agents import SpeechRate
from utils.log import logger

# Constants
VAPI_SECRET_HEADER = "X-VAPI-SIGNATURE"
VAPI_TIMESTAMP_HEADER = "X-VAPI-TIMESTAMP"

# Cartesia voice speed mapping
CARTESIA_SPEED_MAPPING = {
    SpeechRate.slowest: "slowest",
    SpeechRate.slower: "slow",
    SpeechRate.normal: "normal",
    SpeechRate.faster: "fast",
    SpeechRate.fastest: "fastest",
}


def add_voice_speed_if_supported(
    voice_config: Dict[str, Any], speech_rate: SpeechRate
) -> Dict[str, Any]:
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
        voice_config["speed"] = CARTESIA_SPEED_MAPPING.get(speech_rate, "normal")
        logger.debug(
            f"Applied Cartesia speed {voice_config['speed']} for speech rate {speech_rate}"
        )

    return voice_config


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
