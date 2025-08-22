from __future__ import annotations

from enum import StrEnum, auto
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent.client import ClientConfig
from agent.knowledge import KnowledgeConfig
from agent.memory import MemoryConfig
from agent.model import ModelConfig
from agent.tool import ToolConfig
from db.tables.agents import Language, SpeechRate


class AgentFramework(StrEnum):
    AGNO = auto()
    PAL_SIMPLE = auto()


class TransferMode(StrEnum):
    ROLLING_HISTORY = "rolling-history"
    SWAP_SYSTEM_MESSAGE_IN_HISTORY = "swap-system-message-in-history"
    DELETE_HISTORY = "delete-history"
    SWAP_SYSTEM_MESSAGE_IN_HISTORY_AND_REMOVE_TRANSFER_TOOL_MESSAGES = (
        "swap-system-message-in-history-and-remove-transfer-tool-messages"
    )


class AgentPersona(BaseModel):
    name: str
    role: str
    description: Optional[str] = None
    voice_id: Optional[str] = None
    model_mode: Optional[str] = None


class AgentMetadata(BaseModel):
    account_name: str
    agent_id: str
    user_id: str
    session_id: str
    framework: AgentFramework


class SmartDenoisingPlan(BaseModel):
    """Configuration for smart denoising."""

    enabled: bool = True


class FourierDenoisingPlan(BaseModel):
    """Configuration for fourier denoising."""

    enabled: bool = True
    mediaDetectionEnabled: Optional[bool] = None
    baselineOffsetDb: Optional[int] = None
    windowSizeMs: Optional[int] = None
    baselinePercentile: Optional[int] = None


class BackgroundSpeechDenoisingPlan(BaseModel):
    """Configuration for background speech denoising."""

    smartDenoisingPlan: Optional[SmartDenoisingPlan] = None
    fourierDenoisingPlan: Optional[FourierDenoisingPlan] = None


class VoiceConfig(BaseModel):
    enabled: bool = False
    greeting_message: str | None
    voice_id: str | None
    speech_rate: SpeechRate
    background_noise: str
    background_speech_denoising_plan: Optional[BackgroundSpeechDenoisingPlan] = None
    language: Language
    tool_calling_filler_words: dict[str, list[str]] = Field(default_factory=dict)
    chat_filler_words: dict[str, list[str]] = Field(default_factory=dict)
    voice_decoder: Optional[VoiceDecoderConfig] = None
    transcriber: Optional[TranscriberConfig] = None
    start_speaking_plan: Optional[StartSpeakingPlan] = None


class TranscriberConfig(BaseModel):
    """Transcriber configuration"""

    provider: str
    model: str
    language: str
    fallbackPlan: Optional[list[TranscriberConfig]] = None
    # Allow for extra parameters
    model_config = ConfigDict(extra="allow")


# ============================================================================
# START SPEAKING PLAN CONFIGURATION SCHEMAS
# ============================================================================


class TranscriptionEndpointingPlan(BaseModel):
    """Configuration for transcription-based endpointing."""

    on_punctuation_seconds: Optional[float] = Field(
        default=0.1, ge=0, le=3, alias="onPunctuationSeconds"
    )
    on_no_punctuation_seconds: Optional[float] = Field(
        default=1.5, ge=0, le=10, alias="onNoPunctuationSeconds"
    )
    on_number_seconds: Optional[float] = Field(
        default=0.5, ge=0, le=10, alias="onNumberSeconds"
    )

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class StartSpeakingPlan(BaseModel):
    """Configuration for when the assistant should start talking."""

    transcription_endpointing_plan: Optional[TranscriptionEndpointingPlan] = Field(
        default=None, alias="transcriptionEndpointingPlan"
    )

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class VoiceDecoderConfig(BaseModel):
    """Voice configuration."""

    voice_id: str = Field(alias="voiceId")
    voice_model: Optional[str] = Field(default=None, alias="model")
    provider: str
    fallbackPlan: Optional[list[VoiceDecoderConfig]] = None
    chunkPlan: Optional[dict[str, Any]] = None

    model_config = ConfigDict(extra="allow", populate_by_name=True)


# ============================================================================
# VAPI INTEGRATION SCHEMAS
# ============================================================================


class CallerInfo(BaseModel):
    """Structured caller information."""

    sender_identifier: str
    recipient_identifier: str
    call_id: str


class VAPIAssistant(BaseModel):
    """VAPI Assistant configuration model."""

    name: str
    firstMessage: Optional[str] = None
    transcriber: TranscriberConfig
    voice: VoiceDecoderConfig
    backgroundSound: str = "office"
    startSpeakingPlan: Optional[StartSpeakingPlan] = None
    silenceTimeoutSeconds: int = 60
    backgroundDenoisingEnabled: bool = True
    model: Dict[str, Any] = Field(default_factory=dict)
    firstMessageInterruptionsEnabled: bool = False
    firstMessageMode: Literal[
        "assistant-speaks-first",
        "assistant-speaks-first-with-model-generated-message",
        "assistant-waits-for-user",
    ] = "assistant-speaks-first"

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class AssistantDestination(BaseModel):
    """Configuration for assistant transfer destinations."""

    assistantName: str
    message: str = ""  # Spoken to customer before connecting
    description: str  # Used by AI to choose when/how to transfer
    transferMode: TransferMode = Field(
        default=TransferMode.SWAP_SYSTEM_MESSAGE_IN_HISTORY
    )
    type: Literal["assistant"] = "assistant"


class SquadMember(BaseModel):
    """Squad member configuration."""

    assistantId: Optional[str] = None
    assistant: Optional[VAPIAssistant] = None
    assistantDestinations: Optional[List[AssistantDestination]] = None

    @model_validator(mode="after")
    def validate_assistant_or_assistant_id(self):
        # Exactly one of assistant or assistantId must be provided
        if (self.assistant is None) == (self.assistantId is None):
            raise ValueError("Either assistant or assistantId must be provided")
        return self


class SquadConfig(BaseModel):
    """Complete squad configuration."""

    name: str
    members: List[SquadMember]


# ============================================================================
# MULTILINGUAL SQUAD CONFIGURATION in Agent Raw Config
# ============================================================================


class TriageAssistantConfig(VAPIAssistant):
    """Configuration for the triage assistant that extends VAPIAssistant."""

    # Additional fields specific to triage assistant
    transfer_mode: TransferMode = Field(
        default=TransferMode.SWAP_SYSTEM_MESSAGE_IN_HISTORY,
        alias="transferMode",
        exclude=True,
    )


class LanguageAssistantMultilingConfig(VAPIAssistant):
    """Configuration for a specific language assistant in multilingual squad that extends VAPIAssistant."""

    # Additional fields specific to language assistants
    transfer_message: str = Field(default="", alias="transferMessage", exclude=True)
    transfer_description: str = Field(alias="transferDescription", exclude=True)
    transfer_mode: TransferMode = Field(
        default=TransferMode.SWAP_SYSTEM_MESSAGE_IN_HISTORY,
        alias="transferMode",
        exclude=True,
    )


class MultilingualSquadConfig(BaseModel):
    """Complete multilingual squad configuration."""

    triage_assistant: TriageAssistantConfig
    language_assistants: dict[str, LanguageAssistantMultilingConfig]


# ============================================================================
# AGENT CONFIGURATION
# ============================================================================


class AgentConfig(BaseModel):
    persona: AgentPersona

    model: ModelConfig
    memory: MemoryConfig
    knowledge: KnowledgeConfig
    tool: ToolConfig
    voice_config: VoiceConfig

    metadata: AgentMetadata

    client: ClientConfig
    stream: bool = False
    # Additional context added to the end of the system message.
    additional_context: Optional[str] = None
    # Multilingual squad configuration for VAPI integration
    # This is resolved in RawConfigService, so the final type is clean.
    multiling_squad_config: Optional[MultilingualSquadConfig] = None
