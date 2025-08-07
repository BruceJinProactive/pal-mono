from enum import StrEnum, auto
from typing import Optional

from pydantic import BaseModel, ConfigDict

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
    multilingual: bool = False
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
    tool_calling_filler_words: list[str] = []
    chat_filler_words: list[str] = []
    voice_provider: Optional[str] = None


# ============================================================================
# MULTILINGUAL SQUAD CONFIGURATION SCHEMAS
# ============================================================================


class MultilingualTranscriberConfig(BaseModel):
    """Transcriber configuration for multilingual squad."""

    provider: str
    model: str
    language: str

    # Allow for extra parameters
    model_config = ConfigDict(extra="allow")


class MultilingualVoiceConfig(BaseModel):
    """Voice configuration for multilingual squad."""

    voice_id: str
    voice_model: str
    provider: str
    description: Optional[str] = None


class MultilingualModelConfig(BaseModel):
    """Model configuration for multilingual squad."""

    provider: str
    model: str


class TriageAssistantConfig(BaseModel):
    """Configuration for the triage assistant."""

    name: str
    transcriber: MultilingualTranscriberConfig
    voice: MultilingualVoiceConfig
    model: MultilingualModelConfig
    first_message: str
    transfer_mode: str = "swap-system-message-in-history"


class LanguageAssistantMultilingConfig(BaseModel):
    """Configuration for a specific language assistant in multilingual squad."""

    assistant_name: str
    transcriber: MultilingualTranscriberConfig
    voice: MultilingualVoiceConfig
    first_message: str
    transfer_message: str
    transfer_description: str


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
