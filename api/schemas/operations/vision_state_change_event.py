"""Vision State Change Event API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CreateStateChangeEventRequest(BaseModel):
    """Request to create a vision state change event."""

    entity_id: uuid.UUID = Field(..., description="Entity that changed state")
    new_state_id: uuid.UUID = Field(..., description="New state definition ID")
    camera_config_id: uuid.UUID | None = Field(
        default=None, description="Camera config that captured the change"
    )
    previous_state_id: uuid.UUID | None = Field(
        default=None, description="Previous state definition ID"
    )
    confidence: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Confidence score"
    )
    frame_s3_key: str | None = Field(
        default=None, description="S3 key of the frame that triggered the event"
    )
    observed_at: datetime | None = Field(
        default=None, description="Observation timestamp (defaults to now)"
    )
    event_metadata: dict[str, Any] = Field(
        default_factory=dict, description="Arbitrary event metadata"
    )


class StateChangeEventResponse(BaseModel):
    """Response model for a vision state change event."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_id: uuid.UUID
    new_state_id: uuid.UUID
    observed_at: datetime
    camera_config_id: uuid.UUID | None
    previous_state_id: uuid.UUID | None
    confidence: float | None
    frame_s3_key: str | None
    event_metadata: dict[str, Any]


class ListStateChangeEventsResponse(BaseModel):
    """Response for listing state change events."""

    items: list[StateChangeEventResponse]
    total: int
