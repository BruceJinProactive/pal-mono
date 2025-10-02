import uuid
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from db.tables.types import AuthType, IntegrationProvider, IntegrationType
from services.integration_service.schema import (
    CreateIntegrationParams,
    IntegrationCredentials,
    UpdateIntegrationParams,
)


# Request models
class IntegrationRequest(BaseModel):
    """Create Integration Request"""

    provider: IntegrationProvider = Field(..., description="The POS provider")
    integration_type: IntegrationType = Field(
        ..., description="The type of integration"
    )
    auth_type: AuthType = Field(..., description="The authentication type")
    business_id: Optional[str] = Field(
        None, description="Business identifier from the provider"
    )
    raw_config: Optional[Dict] = Field(
        default_factory=dict, description="Additional metadata"
    )
    access_token: Optional[str] = Field(None, description="Access token for OAuth")
    refresh_token: Optional[str] = Field(None, description="Refresh token for OAuth")
    client_id: Optional[str] = Field(None, description="Client ID for OAuth")
    client_secret: Optional[str] = Field(None, description="Client secret for OAuth")
    api_key: Optional[str] = Field(
        None, description="API key for API key authentication"
    )
    expires_at: Optional[datetime] = Field(
        None, description="Expiration timestamp for the integration"
    )

    def to_integration_params(self):
        return CreateIntegrationParams(
            provider=self.provider,
            integration_type=self.integration_type,
            auth_type=self.auth_type,
            business_id=self.business_id,
            raw_config=self.raw_config,
            credentials=IntegrationCredentials(
                access_token=self.access_token,
                refresh_token=self.refresh_token,
                client_id=self.client_id,
                client_secret=self.client_secret,
                api_key=self.api_key,
            ),
            expires_at=self.expires_at,
        )


class UpdateIntegrationRequest(BaseModel):
    business_id: Optional[str] = Field(
        None, description="Business identifier from the provider"
    )
    raw_config: Optional[Dict] = Field(
        default_factory=dict, description="Additional metadata"
    )
    access_token: Optional[str] = Field(None, description="Access token for OAuth")
    refresh_token: Optional[str] = Field(None, description="Refresh token for OAuth")
    client_id: Optional[str] = Field(None, description="Client ID for OAuth")
    client_secret: Optional[str] = Field(None, description="Client secret for OAuth")
    api_key: Optional[str] = Field(
        None, description="API key for API key authentication"
    )
    expires_at: Optional[datetime] = Field(
        None, description="Expiration timestamp for the integration"
    )

    def to_integration_params(self):
        # Only create credentials object if at least one credential field is provided
        credentials = None
        if any(
            [
                self.access_token is not None,
                self.refresh_token is not None,
                self.client_id is not None,
                self.client_secret is not None,
                self.api_key is not None,
            ]
        ):
            credentials = IntegrationCredentials(
                access_token=self.access_token,
                refresh_token=self.refresh_token,
                client_id=self.client_id,
                client_secret=self.client_secret,
                api_key=self.api_key,
            )

        return UpdateIntegrationParams(
            business_id=self.business_id,
            raw_config=self.raw_config,
            credentials=credentials,
            expires_at=self.expires_at,
        )


# Response models
class IntegrationResponse(BaseModel):
    """Integration Response"""

    id: uuid.UUID = Field(..., description="Integration ID")
    account_id: uuid.UUID = Field(..., description="Account ID")
    provider: IntegrationProvider = Field(..., description="The POS provider")
    integration_type: IntegrationType = Field(
        ..., description="The type of integration"
    )
    auth_type: AuthType = Field(..., description="The authentication type")
    business_id: Optional[str] = Field(
        None, description="Business identifier from the provider"
    )
    raw_config: Dict = Field(default_factory=dict, description="Additional metadata")
    access_token: Optional[str] = Field(None, description="Access token for OAuth")
    refresh_token: Optional[str] = Field(None, description="Refresh token for OAuth")
    client_id: Optional[str] = Field(None, description="Client ID for OAuth")
    client_secret: Optional[str] = Field(None, description="Client secret for OAuth")
    api_key: Optional[str] = Field(
        None, description="API key for API key authentication"
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")
    expires_at: Optional[datetime] = Field(None, description="Expiration timestamp")


class IntegrationSummaryResponse(BaseModel):
    """Integration Summary Response"""

    id: uuid.UUID = Field(..., description="Integration ID")
    provider: IntegrationProvider = Field(..., description="The POS provider")
    integration_type: IntegrationType = Field(
        ..., description="The type of integration"
    )
    auth_type: AuthType = Field(..., description="The authentication type")
    business_id: Optional[str] = Field(
        None, description="Business identifier from the provider"
    )
    created_at: datetime = Field(..., description="Creation timestamp")


class ListIntegrationsResponse(BaseModel):
    """List Integrations Response"""

    integrations: List[IntegrationSummaryResponse] = Field(
        ..., description="List of integrations"
    )


# Project Integration models
class CreateProjectIntegrationRequest(BaseModel):
    """Create Project Integration Request"""

    integration_id: uuid.UUID = Field(..., description="Integration ID to link")
    store_identifier: str = Field(..., description="Store identifier for this project")
    tool_name: Optional[str] = Field(
        default=None, description="Name of the tool being linked"
    )
    config: Dict = Field(default_factory=dict, description="Integration configuration")

    def to_project_integration_params(self, project_id: uuid.UUID):
        from services.integration_service.schema import ProjectIntegrationParams

        return ProjectIntegrationParams(
            project_id=str(project_id),
            integration_id=str(self.integration_id),
            store_identifier=self.store_identifier,
            tool_name=self.tool_name,
            config=self.config,
        )


class UpdateProjectIntegrationRequest(BaseModel):
    """Update Project Integration Request"""

    store_identifier: str = Field(..., description="Store identifier for this project")
    tool_name: Optional[str] = Field(
        default=None, description="Name of the tool being linked"
    )
    config: Optional[Dict] = Field(
        default=None, description="Integration configuration overrides"
    )

    def to_project_integration_params(
        self, project_id: uuid.UUID, integration_id: uuid.UUID
    ):
        from services.integration_service.schema import ProjectIntegrationParams

        return ProjectIntegrationParams(
            project_id=str(project_id),
            integration_id=str(integration_id),
            store_identifier=self.store_identifier,
            tool_name=self.tool_name,
            config=self.config,
        )


class ProjectIntegrationResponse(BaseModel):
    """Project Integration Response"""

    id: uuid.UUID = Field(..., description="Project Integration ID")
    project_id: uuid.UUID = Field(..., description="Project ID")
    integration_id: uuid.UUID = Field(..., description="Integration ID")
    store_identifier: str = Field(..., description="Store identifier for this project")
    tool_name: Optional[str] = Field(
        default=None, description="Name of the tool being linked"
    )
    config: Dict = Field(default_factory=dict, description="Integration configuration")
    created_at: datetime = Field(..., description="Creation timestamp")


class ProjectIntegrationSummaryResponse(BaseModel):
    """Project Integration Summary Response"""

    id: uuid.UUID = Field(..., description="Project Integration ID")
    integration_id: uuid.UUID = Field(..., description="Integration ID")
    store_identifier: str = Field(..., description="Store identifier for this project")
    tool_name: Optional[str] = Field(
        default=None, description="Name of the tool being linked"
    )
    config: Dict = Field(default_factory=dict, description="Integration configuration")
    created_at: datetime = Field(..., description="Creation timestamp")


class ListProjectIntegrationsResponse(BaseModel):
    """List Project Integrations Response"""

    project_integrations: List[ProjectIntegrationSummaryResponse] = Field(
        ..., description="List of project integrations"
    )
