import uuid

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
    address: str | None = None
    product_info: str | None = None
    service_instruction: str | None = None
    timezone: str | None = None
    transfer_message: str | None = None
    transfer_phone_number: str | None = None
    reservation_link: str | None = None
    ordering_link: str | None = None
    created_at: int  # timestamp in seconds and UTC tz
    updated_at: int  # timestamp in seconds and UTC tz


class ProjectSummary(BaseModel):
    """Project Summary Model with limited fields"""

    id: uuid.UUID
    name: str
    display_name: str | None
    channel_identifiers: list[str] | None
    timezone: str | None = None
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
    reservation_link: str | None = None
    ordering_link: str | None = None

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
            reservation_link=self.reservation_link,
            ordering_link=self.ordering_link,
        )


class CreateProjectRequest(UpdateProjectRequest):
    """Create Project Request"""

    account_name: str = Field(...)
    name: str
    enable_web_widget: bool = False
    enable_voice: bool = False
    enable_sms: bool = False

    def to_project_params(self):
        params = super().to_project_params()
        params.name = self.name
        return params
