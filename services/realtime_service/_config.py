"""
Configuration for OpenAI Realtime API (OpenAI 2.x).

Provides structured configuration using Pydantic models for session setup.
"""

from typing import Literal

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
    turn_detection_type: Literal["server_vad", "semantic_vad"] = Field(
        default="semantic_vad",
        description="Turn detection type (server_vad or semantic_vad)",
    )
    interrupt_response: bool = Field(
        default=True,
        description="Auto-cancel AI output when user starts speaking (barge-in)",
    )
    eagerness: Literal["low", "medium", "high", "auto"] = Field(
        default="low",
        description="How quickly the model responds (semantic_vad only). low = waits longer.",
    )
    vad_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="VAD activation threshold (server_vad only). Higher = less sensitive to noise.",
    )
    silence_duration_ms: int = Field(
        default=500,
        description="Silence duration before turn ends in ms (server_vad only).",
    )
    prefix_padding_ms: int = Field(
        default=300,
        description="Audio to include before detected speech in ms (server_vad only).",
    )

    # Noise reduction
    noise_reduction_type: Literal["near_field", "far_field"] | None = Field(
        default="far_field",
        description="Noise reduction mode. far_field for phone calls, near_field for headsets, None to disable.",
    )

    def _build_turn_detection(self) -> dict:
        td: dict = {
            "type": self.turn_detection_type,
            "interrupt_response": self.interrupt_response,
        }
        if self.turn_detection_type == "server_vad":
            td["threshold"] = self.vad_threshold
            td["silence_duration_ms"] = self.silence_duration_ms
            td["prefix_padding_ms"] = self.prefix_padding_ms
        elif self.turn_detection_type == "semantic_vad":
            td["eagerness"] = self.eagerness
        return td

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
                    "turn_detection": self._build_turn_detection(),
                    "transcription": {"model": "whisper-1"},
                    **(
                        {"noise_reduction": {"type": self.noise_reduction_type}}
                        if self.noise_reduction_type
                        else {}
                    ),
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
