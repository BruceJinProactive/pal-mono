from enum import StrEnum
from typing import Optional

from pydantic import BaseModel


class KnowledgeProvider(StrEnum):
    LLAMAINDEX = "llamaindex"
    DEFAULT = "default"


class ModelProvider(StrEnum):
    DEFAULT = "default"


class MemoryProvider(StrEnum):
    DEFAULT = "default"


class ToolProvider(StrEnum):
    DEFAULT = "default"


class AgentPersona(BaseModel):
    name: str
    role: str
    description: Optional[str] = None


class ModelConfig(BaseModel):
    provider: ModelProvider = ModelProvider.DEFAULT
    identifier: str = "medium"
    stream: bool = False


class MemoryConfig(BaseModel):
    enabled: bool = True
    provider: MemoryProvider = MemoryProvider.DEFAULT
    identifier: str
    instruction: Optional[str] = None


class KnowledgeConfig(BaseModel):
    enabled: bool = True
    provider: KnowledgeProvider = KnowledgeProvider.DEFAULT
    identifier: str


class ToolConfig(BaseModel):
    provider: ToolProvider = ToolProvider.DEFAULT
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
