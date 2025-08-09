from __future__ import annotations

from enum import StrEnum, auto
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from agent.client import ClientConfig
from agent.knowledge import KnowledgeConfig
from agent.memory import MemoryConfig
from agent.model import ModelConfig
from agent.tool import ToolConfig
from db.tables.agents import Language, SpeechRate


class AgentFramework(StrEnum):
    AGNO = auto()
    PAL_SIMPLE = auto()


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
    background_noise: bool
    background_speech_denoising_plan: Optional[BackgroundSpeechDenoisingPlan] = None
    language: Language
    tool_calling_filler_words: list[str] = Field(default_factory=list)
    chat_filler_words: list[str] = Field(default_factory=list)
    voice_decoder: Optional[VoiceDecoderConfig] = None
    transcriber: Optional[TranscriberConfig] = None


class TranscriberConfig(BaseModel):
    """Transcriber configuration for multilingual squad."""

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


class VoiceDecoderConfig(BaseModel):
    """Voice configuration for multilingual squad."""

    voice_id: str
    voice_model: Optional[str] = None
    provider: str
    chunkPlan: Optional[ChunkPlan] = None
    fallbackPlan: Optional[list[VoiceDecoderConfig]] = None


# ============================================================================
# MULTILINGUAL SQUAD CONFIGURATION SCHEMAS
# ============================================================================


# TODO: Enable custom triage assistant model. If we use custom LLM for triage assistant, we could remove this class
class MultilingualModelConfig(BaseModel):
    """Model configuration for multilingual squad."""

    provider: str = Field(default="openai")
    model: str = Field(default="gpt-4o")


class TriageAssistantConfig(BaseModel):
    """Configuration for the triage assistant."""

    name: str
    transcriber: TranscriberConfig
    voice: VoiceDecoderConfig
    model: MultilingualModelConfig
    first_message: str
    transfer_mode: str = Field(
        default="swap-system-message-in-history", alias="transferMode"
    )

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class LanguageAssistantMultilingConfig(BaseModel):
    """Configuration for a specific language assistant in multilingual squad."""

    assistant_name: str
    transcriber: TranscriberConfig
    voice: VoiceDecoderConfig
    first_message: str
    transfer_message: str
    transfer_description: str

    model_config = ConfigDict(extra="allow")


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
