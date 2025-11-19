from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from agent.knowledge import KnowledgeConfig
from agent.memory import MemoryConfig
from agent.model import ModelConfig
from agent.tool import ToolConfig


class AgentPersona(BaseModel):
    name: str
    role: str
    description: Optional[str] = None


class AgentMetadata(BaseModel):
    account_name: str
    agent_id: str
    user_id: str
    session_id: str


# ============================================================================
# AGENT CONFIGURATION
# ============================================================================


class FeatureConfig(BaseModel):
    chat_filler_words_percentage: int = Field(default=80, ge=0, le=100)
    tool_calling_filler_words_percentage: int = Field(default=80, ge=0, le=100)


class AgentConfig(BaseModel):
    persona: AgentPersona

    model: ModelConfig
    memory: MemoryConfig
    knowledge: KnowledgeConfig
    tool: ToolConfig
    feature_config: FeatureConfig = Field(default_factory=FeatureConfig)

    metadata: AgentMetadata

    stream: bool = False
    # Additional context added to the end of the system message.
    additional_context: Optional[str] = None
