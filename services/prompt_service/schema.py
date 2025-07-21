import uuid
from dataclasses import dataclass, field


@dataclass
class PromptDetailsParams:
    prompt_id: uuid.UUID
    version_number: int
    content: str
    created_by: str
    change_summary: str | None = None


@dataclass
class PromptParams:
    name: str
    channel: list[str] = field(default_factory=list)
    default_prompt_id: str | None = None
    resource_id: uuid.UUID | None = None
    resource_type: str | None = None
    content: str = ""
    change_summary: str | None = None
