from dataclasses import dataclass
from typing import Dict, Optional

from db.tables.types import AuthType, IntegrationType, POSProvider


@dataclass
class IntegrationParams:
    """Parameters for creating/updating integrations."""

    provider: POSProvider
    integration_type: IntegrationType
    auth_type: AuthType
    business_id: Optional[str] = None
    raw_config: Optional[Dict] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    api_key: Optional[str] = None


@dataclass
class UpdateIntegrationParams:
    """Parameters for updating integrations (allows None values for partial updates)."""

    provider: Optional[POSProvider] = None
    integration_type: Optional[IntegrationType] = None
    auth_type: Optional[AuthType] = None
    business_id: Optional[str] = None
    raw_config: Optional[Dict] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    api_key: Optional[str] = None


@dataclass
class ProjectIntegrationParams:
    """Parameters for creating/updating project integrations."""

    project_id: str
    integration_id: str
    store_identifier: str


@dataclass
class CreateIntegrationSecrets:
    """Secrets to be stored for integration."""

    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    api_key: Optional[str] = None
