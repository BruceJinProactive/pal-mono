import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class PromptDetails(BaseModel):
    id: uuid.UUID
    prompt_id: uuid.UUID
    version_number: int
    content: str
    change_summary: str | None = None
    created_by: str
    created_at: datetime
    updated_at: datetime


class Prompt(BaseModel):
    id: uuid.UUID
    name: str
    default_prompt_id: str | None = None
    channel: list[str] = Field(default_factory=list)
    resource_id: uuid.UUID
    resource_type: str
    deleted: bool
    created_at: datetime
    updated_at: datetime
    details: PromptDetails | None = None


class CreatePromptRequest(BaseModel):
    name: str
    default_prompt_id: str | None = None
    channel: list[str] = Field(default_factory=list)
    resource_id: uuid.UUID
    resource_type: str
    content: str
    change_summary: str | None = None
