import uuid

from pydantic import BaseModel, Field


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


class CreateAgentRequest(BaseModel):
    """Create Agent Request"""

    name: str = Field(...)
    account_name: str = Field(...)
    description: str | None = None
    communication_style: str | None = None
    interaction_guidelines: str | None = None
    raw_config: dict | None = None


class UpdateAgentRequest(BaseModel):
    """Update Agent Request"""

    name: str | None = None
    description: str | None = None
    communication_style: str | None = None
    interaction_guidelines: str | None = None
    raw_config: dict | None = None
