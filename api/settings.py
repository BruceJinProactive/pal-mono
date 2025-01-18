from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_core.core_schema import FieldValidationInfo
from pydantic_settings import BaseSettings


class ApiSettings(BaseSettings):
    """Api settings that can be set using environment variables.

    Reference: https://pydantic-docs.helpmanual.io/usage/settings/
    """

    # Api title and version
    title: str = "pal-mono-api"
    version: str = "1.0"

    # Api runtime_env derived from the `runtime_env` environment variable.
    # Valid values include "dev", "lat", "stg", "prd"
    runtime_env: str = "dev"

    # Set to False to disable docs at /docs and /redoc
    docs_enabled: bool = True

    # Cors origin list to allow requests from.
    # This list is set using the set_cors_origin_list validator
    # which uses the runtime_env variable to set the
    # default cors origin list.
    cors_origin_list: Optional[List[str]] = Field(
        default_factory=list, validate_default=True
    )

    @field_validator("runtime_env")
    def validate_runtime_env(cls, runtime_env):
        """Validate runtime_env."""

        valid_runtime_envs = ["dev", "lat", "stg", "prd"]
        if runtime_env not in valid_runtime_envs:
            raise ValueError(f"Invalid runtime_env: {runtime_env}")

        return runtime_env

    @field_validator("cors_origin_list", mode="before")
    def set_cors_origin_list(cls, cors_origin_list, info: FieldValidationInfo):
        valid_cors = cors_origin_list or []

        # Add phidata to cors origin list
        valid_cors.extend(["https://phidata.app", "https://www.phidata.app"])

        runtime_env = info.data.get("runtime_env")
        if runtime_env == "dev" or runtime_env == "lat":
            # 8501 is the default port for streamlit
            # 3000 is the default port for create-react-app
            valid_cors.extend(
                [
                    "http://localhost",
                    "http://localhost:8501",
                    "http://localhost:3000",
                    "http://localhost:5173/",
                ]
            )

        # Proactive AI Lab
        valid_cors.extend(
            [
                "https://proactiveailab.com",
                "https://www.proactiveailab.com",
                "https://console.proactiveailab.com",
                "https://staging-pal-website.vercel.app",
            ]
        )

        # Velotric Bike
        valid_cors.extend(
            [
                "https://velotricbike.com",
                "https://www.velotricbike.com",
            ]
        )

        # Wyze
        valid_cors.extend(
            [
                "http://local.wyze.com",
                "http://local.wyze.com:10003",
                "https://beta-new.my.wyze.com",
                "https://my.wyze.com",
                "https://www.wyze.com",
                "https://wyze.com",
            ]
        )

        return valid_cors


# Create ApiSettings object
api_settings = ApiSettings()
