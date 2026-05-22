import uuid
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, model_validator
from typing_extensions import Self

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
    secret_key: Optional[str] = Field(
        None, description="Secret key used to resolve credentials in the secret store"
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
    auto_fetch: bool = Field(
        default=False,
        description="When True and tool_name=toast_v3, fetch and compile menu from Toast; "
        "config.selected_menus filters which menus to compile (empty or absent = all).",
    )

    @model_validator(mode="after")
    def validate_toast_v3_config(self) -> Self:
        if self.tool_name != "toast_v3":
            return self
        config = self.config
        restaurant_guid = config.get("restaurant_guid", "")
        menu_data = config.get("menu_data")

        if not restaurant_guid or not str(restaurant_guid).strip():
            raise ValueError("toast_v3 config requires restaurant_guid")

        if self.auto_fetch:
            # auto_fetch path: menu_data must be absent (will be populated by fetch)
            if menu_data is not None:
                raise ValueError(
                    "toast_v3 config.menu_data must not be set when auto_fetch=True"
                )
        else:
            # manual path: menu_data required and must be a non-empty dict
            if not isinstance(menu_data, dict) or not menu_data:
                raise ValueError(
                    "toast_v3 config requires a non-empty menu_data when auto_fetch=False"
                )
            takeout_guid = config.get("takeout_dining_option_guid", "")
            if not takeout_guid or not str(takeout_guid).strip():
                raise ValueError(
                    "toast_v3 config requires takeout_dining_option_guid when auto_fetch=False"
                )

        return self

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
    """Update Project Integration Request - fields are optional for PATCH"""

    store_identifier: Optional[str] = Field(
        default=None, description="Store identifier for this project"
    )
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
