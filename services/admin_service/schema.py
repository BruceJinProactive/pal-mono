from dataclasses import dataclass

import db
from db.tables.lead import BusinessSegment, LeadStatus, TargetTier
from services.project_service import ProjectParams


@dataclass
class ProjectSetup:
    params: ProjectParams
    enable_web_widget: bool
    enable_voice: bool
    enable_sms: bool


@dataclass
class UserSessionPreview:
    user_session: db.Conversation
    last_message: db.Message
    message_count: int


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


@dataclass
class LeadFilters:
    """Filter parameters for listing leads"""

    page: int = 1
    page_size: int = 20
    status_filter: list[LeadStatus] | None = None
    segment_filter: list[BusinessSegment] | None = None
    tier_filter: list[TargetTier] | None = None
    keyword: str | None = None
