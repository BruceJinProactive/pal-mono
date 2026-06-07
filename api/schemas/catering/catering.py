import uuid
from datetime import date, datetime, time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from db.tables.catering_request_activities import (
    CateringRequestActivityActorType,
    CateringRequestActivitySource,
    CateringRequestActivityType,
)
from db.tables.catering_requests import FulfillmentType, RequestStatus


class EventBridgeEvent(BaseModel):
    """
    Simplified schema for EventBridge events received from AWS EventBridge.
    Only includes the fields we actually need for processing.
    """

    detail_type: str = Field(alias="detail-type")
    source: Optional[str] = None
    detail: Dict[str, Any]


class CateringEvent(BaseModel):
    """
    Schema for catering event details from EventBridge.
    """

    catering_request_id: str
    idempotency_key: str
    event_data: Optional[Dict[str, Any]] = None


class CreateCateringRequestRequest(BaseModel):
    """
    Request schema for creating a catering request.
    """

    event_date: date
    contact_name: str
    contact_phone_number: str
    event_time: Optional[time] = None
    event_address: Optional[str] = None
    event_detail: Optional[str] = None
    event_fulfillment: Optional[FulfillmentType] = None
    party_size: Optional[int] = None
    idempotency_key: Optional[str] = None


class UpdateCateringRequestRequest(BaseModel):
    """
    Request schema for updating a catering request.
    """

    event_date: Optional[date] = None
    contact_name: Optional[str] = None
    contact_phone_number: Optional[str] = None
    event_time: Optional[time] = None
    event_address: Optional[str] = None
    event_detail: Optional[str] = None
    event_fulfillment: Optional[FulfillmentType] = None
    party_size: Optional[int] = None
    status: Optional[RequestStatus] = None


class CateringRequestActivity(BaseModel):
    """
    Response schema for one catering request activity timeline entry.
    """

    id: uuid.UUID
    catering_request_id: uuid.UUID
    project_id: uuid.UUID
    activity_type: CateringRequestActivityType
    actor_type: CateringRequestActivityActorType
    actor_id: Optional[uuid.UUID] = None
    actor_display_name: str
    description: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    schema_version: int
    source: CateringRequestActivitySource
    occurred_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CateringRequest(BaseModel):
    """
    Response schema for catering request.
    """

    id: uuid.UUID
    project_id: uuid.UUID
    activities: List[CateringRequestActivity] = Field(default_factory=list)
    event_date: date
    contact_name: str
    contact_phone_number: str
    event_time: Optional[time] = None
    event_address: Optional[str] = None
    event_detail: Optional[str] = None
    event_fulfillment: Optional[FulfillmentType] = None
    party_size: Optional[int] = None
    contact_id: Optional[uuid.UUID] = None
    status: RequestStatus
    idempotency_key: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CateringRequestListResponse(BaseModel):
    """
    Response schema for listing catering requests.
    """

    catering_requests: List[CateringRequest]


class CateringRequestActivityListResponse(BaseModel):
    """
    Response schema for listing catering request activities.
    """

    activities: List[CateringRequestActivity]


class PublicCateringRequest(BaseModel):
    """
    Public response schema for catering request detail pages.
    """

    id: uuid.UUID
    event_date: date
    contact_name: str
    event_time: Optional[time] = None
    event_address: Optional[str] = None
    event_detail: Optional[str] = None
    event_fulfillment: Optional[FulfillmentType] = None
    party_size: Optional[int] = None
    status: RequestStatus

    model_config = ConfigDict(from_attributes=True)


class UpdateContactRequest(BaseModel):
    """
    Request schema for updating a contact.
    """

    name: Optional[str] = None
    phone_number: Optional[str] = None
    role: Optional[str] = None
    email: Optional[str] = None


class CreateContactRequest(BaseModel):
    """
    Request schema for creating a contact.
    """

    name: str
    phone_number: str
    role: str
    email: Optional[str] = None


class Contact(BaseModel):
    """
    Response schema for contact.
    """

    id: uuid.UUID
    name: str
    phone_number: str
    role: str
    email: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ContactListResponse(BaseModel):
    """
    Response schema for listing contacts.
    """

    contacts: List[Contact]


class CateringReminderResponse(BaseModel):
    """Response from processing catering inquiry reminders and apologies."""

    success: bool = Field(description="Whether the job completed without errors")
    projects_checked: int = Field(
        description="Number of projects evaluated for reminders"
    )
    reminders_sent: int = Field(description="Number of reminder SMS messages sent")
    apologies_sent: int = Field(
        default=0, description="Number of apology SMS messages sent to requesters"
    )
    errors: list[str] = Field(default_factory=list, description="Error messages if any")
