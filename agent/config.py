from __future__ import annotations

from enum import StrEnum, auto
from typing import Annotated, Any, Dict, List, Literal, Optional, Union

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
    tool_calling_filler_words: list[str] = Field(default_factory=list)
    chat_filler_words: list[str] = Field(default_factory=list)
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


class ChunkPlan(BaseModel):
    """Configuration for chunking model output before sending to voice provider."""

    enabled: bool = True
    minCharacters: Optional[float] = 30
    punctuationBoundaries: Optional[list[str]] = None


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


class SmartEndpointingProvider(StrEnum):
    LIVEKIT = "livekit"
    VAPI = "vapi"


class VapiSmartEndpointing(BaseModel):
    """Configuration for Vapi smart endpointing."""

    provider: Literal[SmartEndpointingProvider.VAPI] = SmartEndpointingProvider.VAPI
    model_config = ConfigDict(extra="allow")


class LivekitSmartEndpointing(BaseModel):
    """Configuration for LiveKit smart endpointing."""

    provider: Literal[SmartEndpointingProvider.LIVEKIT] = (
        SmartEndpointingProvider.LIVEKIT
    )
    wait_function: Optional[str] = Field(
        default="20 + 500 * sqrt(x) + 2500 * x^3", alias="waitFunction"
    )
    model_config = ConfigDict(extra="allow", populate_by_name=True)


# Apply the discriminator to the SmartEndpointing union type
SmartEndpointing = Annotated[
    Union[VapiSmartEndpointing, LivekitSmartEndpointing],
    Field(discriminator="provider"),
]


class StartSpeakingPlan(BaseModel):
    """Configuration for when the assistant should start talking."""

    smart_endpointing_plan: Optional[SmartEndpointing] = Field(
        default=None, alias="smartEndpointingPlan"
    )
    transcription_endpointing_plan: Optional[TranscriptionEndpointingPlan] = Field(
        default=None, alias="transcriptionEndpointingPlan"
    )

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class VoiceDecoderConfig(BaseModel):
    """Voice configuration."""

    voice_id: str = Field(alias="voiceId")
    voice_model: Optional[str] = Field(default=None, alias="model")
    provider: str
    chunkPlan: Optional[ChunkPlan] = None
    fallbackPlan: Optional[list[VoiceDecoderConfig]] = None

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

    name: str = Field(alias="assistant_name")
    firstMessage: Optional[str] = Field(default=None, alias="first_message")
    transcriber: TranscriberConfig
    voice: VoiceDecoderConfig
    backgroundSound: str = Field(alias="background_sound")
    startSpeakingPlan: StartSpeakingPlan = Field(
        default_factory=StartSpeakingPlan, alias="start_speaking_plan"
    )
    silenceTimeoutSeconds: int = Field(default=60, alias="silence_timeout_seconds")
    backgroundDenoisingEnabled: bool = Field(
        default=True, alias="background_denoising_enabled"
    )
    model: Dict[str, Any]
    firstMessageInterruptionsEnabled: bool = Field(
        default=False, alias="first_message_interruptions_enabled"
    )
    firstMessageMode: Literal[
        "assistant-speaks-first",
        "assistant-speaks-first-with-model-generated-message",
        "assistant-waits-for-user",
    ] = Field(default="assistant-speaks-first", alias="first_message_mode")

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
        default=TransferMode.SWAP_SYSTEM_MESSAGE_IN_HISTORY, alias="transferMode"
    )


class LanguageAssistantMultilingConfig(VAPIAssistant):
    """Configuration for a specific language assistant in multilingual squad that extends VAPIAssistant."""

    # Additional fields specific to language assistants
    transfer_message: str = ""
    transfer_description: str
    transfer_mode: TransferMode = Field(
        default=TransferMode.SWAP_SYSTEM_MESSAGE_IN_HISTORY, alias="transferMode"
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
