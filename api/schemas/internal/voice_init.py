"""Request/response schemas for LiveKit voice call initialization."""

from typing import Any

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
    voice_model: str = Field(
        ..., description="Cartesia voice model (sonic-2 or sonic-3)"
    )
    speech_rate: float = Field(
        ..., ge=0.6, le=1.5, description="Speech rate for Cartesia TTS"
    )
    first_message: str = Field(..., description="Greeting message ({{greet}} resolved)")
    language: str = Field(..., description="Language (english, spanish, etc.)")
    stt_model: str = Field(..., description="Deepgram STT model name")
    stt_language: str = Field(
        ..., description="Deepgram STT language code (e.g. en-US)"
    )
    background_sound: str | None = Field(
        default=None, description="Background ambient sound"
    )
    replacements: dict[str, str] = Field(
        default_factory=dict,
        description="Word-to-pronunciation replacement map for TTS preprocessing",
    )
