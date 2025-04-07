from typing import Any

from pydantic import BaseModel, Field


class ClientConfig(BaseModel):
    data: dict[str, Any] = Field(
        default_factory=dict, serialization_alias="client_data"
    )
