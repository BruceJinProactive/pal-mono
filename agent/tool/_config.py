import uuid
from enum import StrEnum, auto
from typing import Any, Dict, List

from pydantic import BaseModel, Field, model_validator
from typing_extensions import Self


class ToolProvider(StrEnum):
    DEFAULT = auto()


class ToolMetadata(BaseModel):
    agent_id: uuid.UUID
    account_id: uuid.UUID
    account_name: str
    user_id: uuid.UUID
    session_id: uuid.UUID
    project_id: uuid.UUID
    timezone: str | None = None
    customer_phone: str | None = None


class ToolIdentifier(BaseModel):
    tool_name: str
    args: Dict[str, Any] = Field(default_factory=dict)

    # Access agent metadata fields (e.g. agent_id, session_id, etc.)
    access_metadata: bool = False

    @model_validator(mode="after")
    def validate_tool(self) -> Self:
        if not self.tool_name:
            raise ValueError("tool_name cannot be empty.")

        return self


class ToolConfig(BaseModel):
    provider: ToolProvider = ToolProvider.DEFAULT
    identifiers: List[ToolIdentifier] = Field(default_factory=list)
    metadata: ToolMetadata
