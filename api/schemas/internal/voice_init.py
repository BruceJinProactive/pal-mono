"""Request/response schemas for LiveKit voice call initialization."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class VoiceInitRequest(BaseModel):
    """Request to initialize a LiveKit voice call."""

    caller_number: str = Field(
        ..., description="Customer phone number (sip.phoneNumber)"
    )
    dialed_number: str = Field(
        ..., description="Business phone number (sip.trunkPhoneNumber)"
    )
    call_id: str = Field(..., description="SIP call identifier (sip.callID)")


class VoiceInitResponse(BaseModel):
    """Response containing voice configuration for a LiveKit agent session."""

    caller_info: dict[str, Any] = Field(
        ..., description="Caller metadata for /v1/chat/completions model field"
    )
    voice_id: str = Field(..., description="Cartesia voice ID")
    speech_rate: float = Field(
        ..., ge=0.6, le=1.5, description="Speech rate for Cartesia TTS"
    )
    first_message: str = Field(..., description="Greeting message ({{greet}} resolved)")
    languages: list[str] = Field(
        ..., description='Languages (e.g. ["english", "spanish"])'
    )
    background_sound: str | None = Field(
        default=None, description="Background ambient sound"
    )
    pronunciation_dict_id: str | None = Field(
        default=None, description="Cartesia pronunciation dictionary ID"
    )


class TurnLatency(BaseModel):
    """Per-turn latency breakdown (all values in milliseconds)."""

    turn_index: int = Field(..., ge=0, description="Zero-based turn index")
    timestamp: float = Field(
        ..., ge=0, description="Unix timestamp when the turn started"
    )

    stt_duration_ms: float = Field(
        default=0.0, ge=0, description="STT processing duration"
    )
    stt_audio_duration_ms: float = Field(
        default=0.0, ge=0, description="Duration of audio sent to STT"
    )

    llm_duration_ms: float = Field(
        default=0.0, ge=0, description="LLM request duration"
    )
    llm_ttft_ms: float = Field(default=0.0, ge=0, description="LLM time to first token")
    llm_tokens_per_second: float = Field(
        default=0.0, ge=0, description="LLM token generation rate"
    )
    llm_prompt_tokens: int = Field(
        default=0, ge=0, description="LLM prompt token count"
    )
    llm_completion_tokens: int = Field(
        default=0, ge=0, description="LLM completion token count"
    )

    tts_ttfb_ms: float = Field(default=0.0, ge=0, description="TTS time to first byte")
    tts_duration_ms: float = Field(
        default=0.0, ge=0, description="TTS request duration"
    )
    tts_audio_duration_ms: float = Field(
        default=0.0, ge=0, description="Duration of audio produced by TTS"
    )


class InterruptionEvent(BaseModel):
    """A single interruption occurrence."""

    turn_index: int = Field(..., ge=0, description="Turn where interruption occurred")
    timestamp: float = Field(
        ..., ge=0, description="Unix timestamp of the interruption"
    )
    source: Literal["stt", "llm", "tts"] = Field(
        ..., description="Pipeline stage that was cancelled"
    )


class CallMetricsReport(BaseModel):
    """Structured per-call metrics from the LiveKit agent worker."""

    turn_latencies_ms: list[TurnLatency] = Field(
        default_factory=list, description="Per-turn latency breakdowns"
    )
    interruption_events: list[InterruptionEvent] = Field(
        default_factory=list, description="Interruption events during the call"
    )


class VoiceEndCallRequest(BaseModel):
    """Request to end a LiveKit voice call."""

    call_id: str = Field(..., description="SIP call identifier")
    caller_number: str = Field(..., description="Customer phone number")
    dialed_number: str = Field(..., description="Business phone number")
    duration_seconds: float = Field(..., description="Call duration in seconds")
    conversation: list[dict[str, Any]] = Field(
        ..., description="Call conversation history"
    )
    close_reason: str = Field(..., description="Reason for call ending")
    audio_recording_s3_uri: str | None = Field(
        default=None, description="S3 URI of the call recording (e.g., s3://bucket/key)"
    )
    metrics: CallMetricsReport | None = Field(
        default=None,
        description="Per-turn latency and interruption metrics from the agent worker",
    )
