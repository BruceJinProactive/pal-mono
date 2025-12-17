from enum import StrEnum, auto
from typing import Optional, Union

from pydantic import BaseModel, ValidationError, model_validator


class KnowledgeProvider(StrEnum):
    LLAMAINDEX = auto()  # Default knowledge provider


### Settings for specific knowledge providers ###
class VectorStoreProvider(StrEnum):
    PINECONE = auto()


class VectorStoreModality(StrEnum):
    TEXT = auto()
    MULTI_MODAL = auto()


class LlamaIndexSettings(BaseModel):
    vector_store_provider: VectorStoreProvider
    vector_store_modality: VectorStoreModality
    index_name: str
    namespace: str


class KnowledgeConfigSettings(BaseModel):
    content: str


### Knowledge Config ###
class KnowledgeConfig(BaseModel):
    enabled: bool = True
    provider: KnowledgeProvider = KnowledgeProvider.LLAMAINDEX
    identifier: Optional[str] = None
    settings: Optional[Union[dict, LlamaIndexSettings]] = None

    @model_validator(mode="before")
    def validate_settings(cls, values):
        provider = values.get("provider")
        if provider == KnowledgeProvider.LLAMAINDEX:
            # Validate settings if provider LLamaIndex is selected
            settings = values.get("settings")
            if not settings:
                raise ValueError(
                    "KnowledgeConfig settings required for provider 'LlamaIndex'"
                    "but not found in config."
                )

            try:
                # If LlamaIndexSettings schema is satisfied, create instance
                settings = LlamaIndexSettings.model_validate(settings)
            except ValidationError as e:
                raise ValueError(
                    "Invalid KnowledgeConfig settings for provider 'LlamaIndex'."
                ) from e

            values["settings"] = settings

        # If no validate errors, return values
        return values
