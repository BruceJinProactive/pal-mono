from enum import StrEnum, auto

from pydantic import BaseModel


class ToolProvider(StrEnum):
    DEFAULT = auto()


class ToolConfig(BaseModel):
    provider: ToolProvider = ToolProvider.DEFAULT
    identifiers: list[str]
