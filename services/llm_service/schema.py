from enum import Enum


class ModelOptions(Enum):
    """
    Enum that lists all available Portkey configs
    and AWS Secrets Manager secret storing config id
    """

    GPT_4O = ("gpt-4o", "PORTKEY_CONFIG_GPT4O")

    @property
    def model_name(self) -> str:
        """
        Return the model name associated with this option
        """
        return self.value[0]

    @property
    def env_key(self) -> str:
        """
        Return the environment variable key associated with this option
        """
        return self.value[1]
