from enum import StrEnum, auto

from pydantic import BaseModel


class ModelProvider(StrEnum):
    OPENAI = auto()


class ModelConfig(BaseModel):
    provider: ModelProvider = ModelProvider.OPENAI
    identifier: str = "gpt-4o"
