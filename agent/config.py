from enum import StrEnum, auto
from typing import Optional

from pydantic import BaseModel

from agent.client import ClientConfig
from agent.knowledge import KnowledgeConfig
from agent.memory import MemoryConfig
from agent.model import ModelConfig
from agent.tool import ToolConfig


class AgentFramework(StrEnum):
    AGNO = auto()
    CREWAI = auto()


class AgentPersona(BaseModel):
    name: str
    role: str
    description: Optional[str] = None
    voice_id: Optional[str] = None


class AgentMetadata(BaseModel):
    account_name: str
    agent_id: str
    user_id: str
    session_id: str
    framework: AgentFramework


class AgentConfig(BaseModel):
    persona: AgentPersona

    model: ModelConfig
    memory: MemoryConfig
    knowledge: KnowledgeConfig
    tool: ToolConfig

    metadata: AgentMetadata

    client: ClientConfig
    stream: bool = False
    # Eventually we will remove agno storage.
    # Therefore, we simply just add the switch to turn off agno storage now
    storage_enabled: bool = True
    # Additional context added to the end of the system message.
    additional_context: Optional[str] = None
