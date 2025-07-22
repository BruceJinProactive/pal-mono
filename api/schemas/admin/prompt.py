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


class SystemPrompt(BaseModel):
    id: str
    title: str
    instructions: str
    channels: list[str] | None = None
    agent_types: list[str] | None = None
    plan_tiers: list[str] | None = None
    pos_vendors: list[str] | None = None


class CreatePromptRequest(BaseModel):
    name: str
    default_prompt_id: str | None = None
    channel: list[str] = Field(default_factory=list)
    resource_id: uuid.UUID
    resource_type: str
    content: str
    change_summary: str | None = None


class UpdatePromptRequest(BaseModel):
    name: str | None = None
    default_prompt_id: str | None = None
    channel: list[str] | None = None
    content: str | None = None
    change_summary: str | None = None
