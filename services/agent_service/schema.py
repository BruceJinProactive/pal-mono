from dataclasses import dataclass
from typing import Optional

from agent.config import BackgroundSpeechDenoisingPlan
from db.tables.agents import AgentType, Language, SpeechRate


@dataclass
class AgentParams:
    name: str | None = None
    description: str | None = None
    communication_style: str | None = None
    interaction_guidelines: str | None = None
    raw_config: dict | None = None
    agent_type: AgentType | None = None
    voice_id: str | None = None
    greeting_message: str | None = None
    speech_rate: SpeechRate | None = None
    background_noise: bool | None = None
    background_speech_denoising_plan: Optional[BackgroundSpeechDenoisingPlan] = None
    language: Language | None = None
    filler_words: dict | None = None
    memory_enabled: bool | None = None
