"""
Configuration for OpenAI Realtime API (OpenAI 2.x).

Provides structured configuration using Pydantic models for session setup.
"""

from pydantic import BaseModel, Field


class RealtimeConfig(BaseModel):
    """Configuration for OpenAI Realtime API session (OpenAI 2.x)."""

    # Audio format (OpenAI 2.x uses flat structure)
    input_audio_format: str = Field(
        default="g711_ulaw",
        description="Input audio format (g711_ulaw, g711_alaw, or pcm16)",
    )
    output_audio_format: str = Field(
        default="g711_ulaw",
        description="Output audio format (g711_ulaw, g711_alaw, or pcm16)",
    )

    # Voice settings
    voice_id: str = Field(
        default="alloy",
        description="OpenAI voice ID (alloy, echo, fable, onyx, nova, shimmer)",
    )
    temperature: float = Field(
        default=0.8,
        ge=0.6,
        le=1.2,
        description="Model temperature (NOTE: Not used in session.update - reserved for future per-response config)",
    )

    # System configuration
    system_prompt: str = Field(
        description="System instructions for the AI assistant",
    )

    # VAD configuration
    turn_detection_type: str = Field(
        default="server_vad",
        description="Turn detection type (server_vad or none)",
    )

    # Tool definitions (OpenAI function format)
    tools: list[dict] = Field(
        default_factory=list,
        description="List of tool/function definitions",
    )

    def to_session_config(self) -> dict:
        """
        Generate OpenAI 2.x session configuration.

        Returns flat structure required by session.update() API.
        See: https://platform.openai.com/docs/api-reference/realtime-sessions/update

        Note: temperature is NOT supported in session.update() for Realtime API.
        It can only be set per-response, not at session level.

        Returns:
            dict: Session configuration for OpenAI Realtime API
        """
        config = {
            "type": "realtime",  # Required field
            "modalities": ["audio"],
            "instructions": self.system_prompt,
            "voice": self.voice_id,
            "input_audio_format": self.input_audio_format,
            "output_audio_format": self.output_audio_format,
            "turn_detection": {"type": self.turn_detection_type},
        }

        # Only include tools if any are defined
        if self.tools:
            config["tools"] = self.tools

        return config
