from enum import Enum, StrEnum, auto

from pydantic import BaseModel


class ModelProvider(StrEnum):
    OPENAI = auto()


class ModelConfig(BaseModel):
    provider: ModelProvider = ModelProvider.OPENAI
    identifier: str = "gpt-4o"


class ModelOptions(Enum):
    """
    Enum that lists all available Azure OpenAI deployments
    and their corresponding model names
    """

    GPT_4O = ("gpt-4o", "AZURE_OPENAI_DEPLOYMENT_GPT4O")

    @property
    def model_name(self) -> str:
        """
        Return the model name associated with this option
        """
        return self.value[0]

    @property
    def env_key(self) -> str:
        """
        Return the environment variable key for the Azure deployment name
        """
        return self.value[1]
