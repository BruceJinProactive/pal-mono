from enum import StrEnum, auto
from typing import Optional

from pydantic import BaseModel


class MemoryProvider(StrEnum):
    DEFAULT = auto()
    PROMPT = auto()


class MemoryConfig(BaseModel):
    enabled: bool = True
    provider: MemoryProvider = MemoryProvider.DEFAULT
    identifier: str
    instruction: Optional[str] = None
