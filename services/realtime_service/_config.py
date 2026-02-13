"""
Configuration for OpenAI Realtime API (OpenAI 2.x).

Provides structured configuration using Pydantic models for session setup.
"""

from pydantic import BaseModel, Field


class RealtimeConfig(BaseModel):
    """Configuration for OpenAI Realtime API session (OpenAI 2.x)."""

    # Audio format (OpenAI 2.x uses nested audio.input/output structure)
    input_audio_format: str = Field(
        default="audio/pcmu",
        description="Input audio format (audio/pcmu, audio/pcma, or audio/pcm)",
    )
    output_audio_format: str = Field(
        default="audio/pcmu",
        description="Output audio format (audio/pcmu, audio/pcma, or audio/pcm)",
    )

    # Voice settings
    voice_id: str = Field(
        default="alloy",
        description="OpenAI voice ID (alloy, echo, fable, onyx, nova, shimmer)",
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

    def to_session_config(self) -> dict:
        """
        Generate OpenAI 2.x session configuration.

        Returns nested structure required by session.update() API.
        See: https://platform.openai.com/docs/api-reference/realtime-sessions/update

        Note: temperature is NOT supported in session.update() for Realtime API.
        It can only be set per-response, not at session level.

        Returns:
            dict: Session configuration for OpenAI Realtime API
        """
        config = {
            "type": "realtime",  # Required field
            "audio": {  # Nested audio configuration
                "input": {
                    "format": {"type": self.input_audio_format},
                    "turn_detection": {"type": self.turn_detection_type},
                    "transcription": {"model": "whisper-1"},  # Enable transcription
                },
                "output": {
                    "format": {"type": self.output_audio_format},
                    "voice": self.voice_id,
                },
            },
            "instructions": self.system_prompt,
            "output_modalities": ["audio"],
        }

        return config
