from enum import StrEnum, auto
from typing import Optional

from pydantic import BaseModel

from agent.client import ClientConfig
from agent.knowledge import KnowledgeConfig
from agent.memory import MemoryConfig
from agent.model import ModelConfig
from agent.tool import ToolConfig
from db.tables.agents import SpeechRate


class AgentFramework(StrEnum):
    AGNO = auto()
    CREWAI = auto()


class AgentPersona(BaseModel):
    name: str
    role: str
    description: Optional[str] = None
    voice_id: Optional[str] = None
    multilingual: bool = False


class AgentMetadata(BaseModel):
    account_name: str
    agent_id: str
    user_id: str
    session_id: str
    framework: AgentFramework


class StorageProvider(StrEnum):
    AGNO = auto()
    PALSTORAGE = auto()


class VoiceConfig(BaseModel):
    enabled: bool = False
    greeting_message: str | None
    voice_id: str | None
    speech_rate: SpeechRate
    background_noise: bool


class AgentConfig(BaseModel):
    persona: AgentPersona

    model: ModelConfig
    memory: MemoryConfig
    knowledge: KnowledgeConfig
    tool: ToolConfig
    storage_provider: StorageProvider
    voice_config: VoiceConfig

    metadata: AgentMetadata

    client: ClientConfig
    stream: bool = False
    # Additional context added to the end of the system message.
    additional_context: Optional[str] = None
