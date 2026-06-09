from dataclasses import dataclass
from typing import TypedDict

import db
from db.tables.lead import BusinessSegment, LeadStatus, TargetTier
from services.project_service import ProjectParams


class CreatedProjectInfo(TypedDict):
    """Type definition for project information returned from onboarding"""

    project_id: str
    project_name: str
    agent_id: str
    enable_web_widget: bool


@dataclass
class ProjectSetup:
    params: ProjectParams
    enable_web_widget: bool


@dataclass(frozen=True, slots=True)
class ChannelInfo:
    handle: str
    name: str

    def __str__(self) -> str:  # keep the nice printable form
        return f"{self.name}: {self.handle}"


@dataclass
class UserSessionPreview:
    conversation: db.Conversation
    last_message: db.Message | None
    message_count: int
    order_number: str | None = None
    has_order: bool = False


@dataclass(frozen=True, slots=True)
class OrderDisplayInfo:
    order_number: str | None = None
    has_order: bool = False


@dataclass
class CognitoUserSession:
    user_sub: str
    access_token: str
    refresh_token: str
    id_token: str
    expires_in: int


@dataclass
class CognitoUser:
    email: str
    name: str
    status: str | None = None
    session: CognitoUserSession | None = None


@dataclass
class LeadParams:
    """Parameters for creating or updating a lead"""

    business_name: str | None = None
    business_address: str | None = None
    logo_uri: str | None = None
    segment: BusinessSegment | None = None
    tier: TargetTier | None = None
    owner: str | None = None
    hubspot_record_id: str | None = None
    status: LeadStatus | None = None
    notes: str | None = None
    pos: str | None = None
    channels: list[str] | None = None
    contract_signed: bool | None = None


@dataclass
class LeadFilters:
    """Filter parameters for listing leads"""

    page: int = 1
    page_size: int = 20
    status_filter: list[LeadStatus] | None = None
    segment_filter: list[BusinessSegment] | None = None
    tier_filter: list[TargetTier] | None = None
    keyword: str | None = None
