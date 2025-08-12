from typing import Optional

from pydantic import BaseModel


class MemoryConfig(BaseModel):
    enabled: bool = True
    identifier: str
    instruction: Optional[str] = None
