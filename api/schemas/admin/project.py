import uuid

from pydantic import BaseModel, Field


class Project(BaseModel):
    """Project Model"""

    id: uuid.UUID
    name: str
    display_name: str | None
    raw_config: dict
    channel_identifiers: list[str]
    agent_id: uuid.UUID
    account_id: uuid.UUID


class CreateProjectRequest(BaseModel):
    """Create Project Request"""

    account_id: uuid.UUID = Field(...)
    agent_id: uuid.UUID = Field(...)
    name: str = Field(...)
    display_name: str | None = None
    raw_config: dict | None = None
    channel_identifiers: list[str] | None = None


class UpdateProjectRequest(BaseModel):
    """Update Project Request"""

    agent_id: uuid.UUID | None = None
    name: str | None = None
    display_name: str | None = None
    raw_config: dict | None = None
    channel_identifiers: list[str] | None = None
