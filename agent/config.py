from typing import Optional

from pydantic import BaseModel


class AgentPersona(BaseModel):
    name: str
    role: str
    description: Optional[str] = None


class ModelConfig(BaseModel):
    provider: str = "default"
    identifier: str = "medium"
    stream: bool = False


class MemoryConfig(BaseModel):
    enabled: bool = True
    provider: str = "default"
    identifier: str
    instruction: Optional[str] = None


class KnowledgeConfig(BaseModel):
    enabled: bool = True
    provider: str = "default"
    identifier: str


class ToolConfig(BaseModel):
    provider: str = "default"
    identifiers: list[str]


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
