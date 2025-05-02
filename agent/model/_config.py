from enum import StrEnum, auto

from pydantic import BaseModel


class ModelProvider(StrEnum):
    DEFAULT = auto()


class ModelConfig(BaseModel):
    provider: ModelProvider = ModelProvider.DEFAULT
    identifier: str = "medium"
