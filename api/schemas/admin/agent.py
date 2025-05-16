import uuid
from enum import Enum

from pydantic import BaseModel, Field


class AgentType(str, Enum):
    """Agent Type Enum"""

    GENERAL = "general"
    ORDERING = "ordering"
    SALES = "sales"


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


class AgentSummary(BaseModel):
    """Agent Summary Model with limited fields"""

    id: uuid.UUID
    name: str
    agent_type: AgentType | None


class CreateAgentRequest(BaseModel):
    """Create Agent Request"""

    name: str = Field(...)
    account_name: str = Field(...)
    description: str | None = None
    communication_style: str | None = None
    interaction_guidelines: str | None = None
    raw_config: dict | None = None
    agent_type: AgentType = Field(default=AgentType.GENERAL)


class UpdateAgentRequest(BaseModel):
    """Update Agent Request"""

    name: str | None = None
    description: str | None = None
    communication_style: str | None = None
    interaction_guidelines: str | None = None
    raw_config: dict | None = None
    agent_type: AgentType | None = None
