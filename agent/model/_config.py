from enum import Enum, StrEnum, auto

from pydantic import BaseModel


class ModelProvider(StrEnum):
    TRUEFOUNDRY = auto()


class ModelConfig(BaseModel):
    provider: ModelProvider = ModelProvider.TRUEFOUNDRY
    identifier: str = "gpt-4o"


class ModelOptions(Enum):
    """
    Enum that lists all available TrueFoundry deployments
    and their corresponding model names
    """

    GPT_4O = ("gpt-4o", "TRUEFOUNDRY_MODEL_ID")

    @property
    def model_name(self) -> str:
        """
        Return the model name associated with this option
        """
        return self.value[0]

    @property
    def env_key(self) -> str:
        """
        Return the environment variable key for the provider
        """
        return self.value[1]
