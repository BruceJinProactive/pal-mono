import uuid

from pydantic import BaseModel, Field, SecretStr, field_validator

from db.tables.pos_integration import POSState
from db.tables.types import POSProvider


class POSIntegrationRequest(BaseModel):
    """Request to setup POS integration for a project"""

    project_id: uuid.UUID
    store_identifier: str
    provider: POSProvider
    state: POSState = POSState.ACTIVATE
    client_key: str = Field(..., repr=False, min_length=1)
    client_secret: SecretStr = Field(..., repr=False)

    @field_validator("client_key")
    @classmethod
    def validate_client_key(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("client_key cannot be empty or whitespace")
        return v.strip()

    # … rest of the model …
