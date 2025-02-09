from enum import StrEnum, auto
from typing import Any, Dict, List

from pydantic import BaseModel, Field


class ToolProvider(StrEnum):
    DEFAULT = auto()


class ToolIdentifier(BaseModel):
    tool_name: str
    args: Dict[str, Any] = Field(default_factory=dict)


class ToolConfig(BaseModel):
    provider: ToolProvider = ToolProvider.DEFAULT
    identifiers: List[ToolIdentifier]
