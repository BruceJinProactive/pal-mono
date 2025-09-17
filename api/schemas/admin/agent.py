import uuid

from pydantic import BaseModel, Field

from db.tables.agents import AgentType, Language, SpeechRate
from services.agent_service import AgentParams


class Agent(BaseModel):
    """Agent Model"""

    id: uuid.UUID
    name: str
    description: str | None
    communication_style: str | None
    interaction_guidelines: str | None
    raw_config: dict
    created_at: int  # timestamp in seconds and UTC tz
    updated_at: int  # timestamp in seconds and UTC tz
    projects: list[str]
    account_id: uuid.UUID
    agent_type: AgentType | None
    voice_id: str | None = None
    greeting_message: str | None = None
    speech_rate: SpeechRate | None = None
    background_noise: bool | None = None
    language: Language | None = None


class AgentSummary(BaseModel):
    """Agent Summary Model with limited fields"""

    id: uuid.UUID
    name: str
    agent_type: AgentType | None
    language: Language | None


class UpdateAgentRequest(BaseModel):
    """Update Agent Request"""

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
    language: Language | None = None
    expected_version: int | None = None

    def to_agent_params(self) -> AgentParams:
        return AgentParams(
            name=self.name,
            description=self.description,
            communication_style=self.communication_style,
            interaction_guidelines=self.interaction_guidelines,
            raw_config=self.raw_config,
            agent_type=self.agent_type,
            voice_id=self.voice_id,
            greeting_message=self.greeting_message,
            speech_rate=self.speech_rate,
            background_noise=self.background_noise,
            language=self.language,
        )


class CreateAgentRequest(UpdateAgentRequest):
    """Create Agent Request"""

    account_name: str = Field(...)
