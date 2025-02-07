from typing import Optional

from pydantic import BaseModel

from .knowledge import KnowledgeConfig
from .memory import MemoryConfig
from .model import ModelConfig
from .tool import ToolConfig


class AgentPersona(BaseModel):
    name: str
    role: str
    description: Optional[str] = None


class AgentMetadata(BaseModel):
    account_name: str
    agent_id: str
    user_id: str
    session_id: str
    framework: str


class AgentConfig(BaseModel):
    persona: AgentPersona

    model: ModelConfig
    memory: MemoryConfig
    knowledge: KnowledgeConfig
    tool: ToolConfig

    metadata: AgentMetadata
