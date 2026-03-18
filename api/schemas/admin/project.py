import uuid
from typing import List

from pydantic import BaseModel, Field

from services.project_service import ProjectParams


class Project(BaseModel):
    """Project Model"""

    id: uuid.UUID
    name: str
    display_name: str | None
    raw_config: dict
    channel_identifiers: list[str]
    agent_id: uuid.UUID
    account_id: uuid.UUID
    store_hours: str | None = None
    business_hours: dict | None = None
    address: str | None = None
    product_info: str | None = None
    service_instruction: str | None = None
    timezone: str | None = None
    transfer_message: str | None = None
    transfer_phone_number: str | None = None
    show_agent_caller_id: bool = False
    reservation_link: str | None = None
    ordering_link: str | None = None
    google_place_id: str | None = None
    call_forwarding_setup_completed: bool = False
    created_at: int  # timestamp in seconds and UTC tz
    updated_at: int  # timestamp in seconds and UTC tz


class ProjectSummary(BaseModel):
    """Project Summary Model with limited fields"""

    id: uuid.UUID
    name: str
    display_name: str | None
    channel_identifiers: list[str] | None
    timezone: str | None = None
    address: str | None = None
    google_place_id: str | None = None
    created_at: int  # timestamp in seconds and UTC tz
    updated_at: int  # timestamp in seconds and UTC tz


class UpdateProjectRequest(BaseModel):
    """Update Project Request"""

    agent_id: uuid.UUID | None = None
    display_name: str | None = None
    raw_config: dict | None = None
    channel_identifiers: list[str] | None = None
    store_hours: str | None = None
    address: str | None = None
    product_info: str | None = None
    service_instruction: str | None = None
    timezone: str | None = None
    transfer_message: str | None = None
    transfer_phone_number: str | None = None
    show_agent_caller_id: bool | None = None
    reservation_link: str | None = None
    ordering_link: str | None = None
    google_place_id: str | None = None
    call_forwarding_setup_completed: bool | None = None
    expected_version: int | None = None

    def to_project_params(self):
        return ProjectParams(
            display_name=self.display_name,
            agent_id=self.agent_id,
            raw_config=self.raw_config,
            channel_identifiers=self.channel_identifiers,
            store_hours=self.store_hours,
            address=self.address,
            product_info=self.product_info,
            service_instruction=self.service_instruction,
            timezone=self.timezone,
            transfer_message=self.transfer_message,
            transfer_phone_number=self.transfer_phone_number,
            show_agent_caller_id=self.show_agent_caller_id,
            reservation_link=self.reservation_link,
            ordering_link=self.ordering_link,
            google_place_id=self.google_place_id,
            call_forwarding_setup_completed=self.call_forwarding_setup_completed,
        )


class CreateProjectRequest(UpdateProjectRequest):
    """Create Project Request"""

    account_name: str = Field(...)
    name: str
    enable_web_widget: bool = False
    subscription_id: uuid.UUID | None = None

    def to_project_params(self):
        params = super().to_project_params()
        params.name = self.name
        return params


class LocationProjectData(BaseModel):
    """Single location data for project creation"""

    name: str = Field(..., description="Unique project name")
    display_name: str = Field(..., description="Human-readable display name")
    address: str | None = Field(None, description="Full address of the location")
    store_hours: str | None = Field(None, description="Store operating hours")
    transfer_phone_number: str | None = Field(
        None, description="Phone number for transfers"
    )
    timezone: str | None = Field(None, description="Timezone for the location")
    product_info: str | None = Field(None, description="Product/menu information")
    service_instruction: str | None = Field(
        None, description="Service instructions for the agent"
    )
    ordering_link: str | None = Field(None, description="Online ordering link")
    reservation_link: str | None = Field(None, description="Reservation link")
    google_place_id: str | None = Field(None, description="Google Place ID")

    def to_project_params(self, agent_id: uuid.UUID) -> ProjectParams:
        """Convert to ProjectParams for service layer"""
        return ProjectParams(
            name=self.name,
            display_name=self.display_name,
            agent_id=agent_id,
            address=self.address,
            store_hours=self.store_hours,
            transfer_phone_number=self.transfer_phone_number,
            timezone=self.timezone,
            product_info=self.product_info,
            service_instruction=self.service_instruction,
            ordering_link=self.ordering_link,
            reservation_link=self.reservation_link,
            google_place_id=self.google_place_id,
        )


class BatchCreateProjectsRequest(BaseModel):
    """Request schema for batch project creation"""

    account_name: str = Field(..., description="Account name to create projects under")
    agent_id: uuid.UUID = Field(..., description="Agent ID to use for all projects")
    locations: List[LocationProjectData] = Field(
        ..., min_length=1, description="List of location data for creating projects"
    )


class ProjectCreationResult(BaseModel):
    """Result of creating a single project"""

    project_name: str
    project_id: uuid.UUID | None = None
    display_name: str | None = None
    success: bool
    error_message: str | None = None


class BatchCreateProjectsResponse(BaseModel):
    """Response schema for batch project creation"""

    account_name: str
    total_requested: int
    total_created: int
    total_failed: int
    results: List[ProjectCreationResult]

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage"""
        if self.total_requested == 0:
            return 0.0
        return (self.total_created / self.total_requested) * 100.0


class ProjectUpdateData(BaseModel):
    """Single project update data"""

    project_id: uuid.UUID = Field(..., description="ID of the project to update")
    agent_id: uuid.UUID | None = None
    display_name: str | None = None
    raw_config: dict | None = None
    channel_identifiers: list[str] | None = None
    store_hours: str | None = None
    address: str | None = None
    product_info: str | None = None
    service_instruction: str | None = None
    timezone: str | None = None
    transfer_message: str | None = None
    transfer_phone_number: str | None = None
    show_agent_caller_id: bool | None = None
    reservation_link: str | None = None
    ordering_link: str | None = None
    google_place_id: str | None = None
    call_forwarding_setup_completed: bool | None = None
    expected_version: int | None = None

    def to_project_params(self):
        return ProjectParams(
            display_name=self.display_name,
            agent_id=self.agent_id,
            raw_config=self.raw_config,
            channel_identifiers=self.channel_identifiers,
            store_hours=self.store_hours,
            address=self.address,
            product_info=self.product_info,
            service_instruction=self.service_instruction,
            timezone=self.timezone,
            transfer_message=self.transfer_message,
            transfer_phone_number=self.transfer_phone_number,
            show_agent_caller_id=self.show_agent_caller_id,
            reservation_link=self.reservation_link,
            ordering_link=self.ordering_link,
            google_place_id=self.google_place_id,
            call_forwarding_setup_completed=self.call_forwarding_setup_completed,
        )


class BatchUpdateProjectsRequest(BaseModel):
    """Request schema for batch project updates"""

    account_name: str = Field(..., description="Account name that owns the projects")
    project_updates: List[ProjectUpdateData] = Field(
        ..., min_length=1, description="List of project updates to apply"
    )


class ProjectUpdateResult(BaseModel):
    """Result of updating a single project"""

    project_id: uuid.UUID | None = None
    project_name: str
    display_name: str | None = None
    success: bool
    error_message: str | None = None


class BatchUpdateProjectsResponse(BaseModel):
    """Response schema for batch project updates"""

    account_name: str
    total_requested: int
    total_updated: int
    total_failed: int
    results: List[ProjectUpdateResult]

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage"""
        if self.total_requested == 0:
            return 0.0
        return (self.total_updated / self.total_requested) * 100.0


class BatchDeleteProjectsRequest(BaseModel):
    """Request schema for batch project deletion"""

    account_name: str = Field(..., description="Account name that owns the projects")
    project_ids: List[uuid.UUID] = Field(
        ..., min_length=1, description="List of project IDs to delete"
    )


class ProjectDeletionResult(BaseModel):
    """Result of deleting a single project"""

    project_id: uuid.UUID
    project_name: str
    success: bool
    error_message: str | None = None


class BatchDeleteProjectsResponse(BaseModel):
    """Response schema for batch project deletion"""

    account_name: str
    total_requested: int
    total_deleted: int
    total_failed: int
    results: List[ProjectDeletionResult]

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage"""
        if self.total_requested == 0:
            return 0.0
        return (self.total_deleted / self.total_requested) * 100.0
