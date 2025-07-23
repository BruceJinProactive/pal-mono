import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from db.tables.types import AuthType, IntegrationProvider, IntegrationType


@dataclass
class IntegrationCredentials:
    """Authentication credentials for integrations."""

    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    api_key: Optional[str] = None


@dataclass
class CreateIntegrationParams:
    """Parameters for creating integrations - all required fields must be provided."""

    provider: IntegrationProvider
    integration_type: IntegrationType
    auth_type: AuthType
    credentials: IntegrationCredentials
    business_id: Optional[str] = None
    raw_config: Optional[Dict] = None
    expires_at: Optional[datetime] = None


@dataclass
class UpdateIntegrationParams:
    """Parameters for updating integrations - all fields are optional for partial updates."""

    business_id: Optional[str] = None
    raw_config: Optional[Dict] = None
    credentials: Optional[IntegrationCredentials] = None


@dataclass
class ProjectIntegrationParams:
    """Parameters for creating/updating project integrations."""

    project_id: str
    integration_id: str
    store_identifier: str


@dataclass
class IntegrationDetail:
    id: uuid.UUID
    account_id: uuid.UUID
    integration_type: IntegrationType
    provider: IntegrationProvider
    auth_type: AuthType
    business_id: Optional[str]
    raw_config: dict[str, Any]
    access_token: Optional[str]
    refresh_token: Optional[str]
    client_id: Optional[str]
    client_secret: Optional[str]
    api_key: Optional[str]
    created_at: datetime
    updated_at: datetime | None
