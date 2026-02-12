"""
Configuration for OpenAI Realtime API (OpenAI 2.x).

Provides structured configuration using Pydantic models for session setup.
"""

from pydantic import BaseModel, Field


class RealtimeConfig(BaseModel):
    """Configuration for OpenAI Realtime API session (OpenAI 2.x)."""

    # Audio format (OpenAI 2.x uses nested structure)
    input_audio_format: str = Field(
        default="audio/pcmu",
        description="Input audio format (audio/pcmu = G.711 µ-law)",
    )
    output_audio_format: str = Field(
        default="audio/pcmu",
        description="Output audio format (audio/pcmu = G.711 µ-law)",
    )

    # Voice settings
    voice_id: str = Field(
        default="alloy",
        description="OpenAI voice ID (alloy, echo, fable, onyx, nova, shimmer)",
    )
    temperature: float = Field(
        default=0.7,
        ge=0.6,
        le=1.2,
        description="Model temperature for response generation (Realtime API range: 0.6-1.2)",
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

        Returns nested structure required by production Realtime API.

        Returns:
            dict: Session configuration for OpenAI Realtime API
        """
        config = {
            "type": "realtime",
            "audio": {
                "input": {
                    "format": {"type": self.input_audio_format},
                    "turn_detection": {"type": self.turn_detection_type},
                },
                "output": {
                    "format": {"type": self.output_audio_format},
                    "voice": self.voice_id,
                },
            },
            "instructions": self.system_prompt,
            "output_modalities": ["audio"],
            "temperature": self.temperature,
        }

        # Only include tools if any are defined
        if self.tools:
            config["tools"] = self.tools

        return config
