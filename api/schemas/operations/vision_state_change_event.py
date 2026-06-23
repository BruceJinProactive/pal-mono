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
    manually_adjusted: bool = Field(
        default=False,
        description="Whether rule events generated from this state change were manually added",
    )
    is_test: bool | None = Field(
        default=None, description="Whether this event is from a test run"
    )
    test_group: str | None = Field(
        default=None, description="Test group identifier for grouping test events"
    )


class UpdateStateChangeEventRequest(BaseModel):
    """Request to update a vision state change event's metadata."""

    is_test: bool | None = Field(
        default=None, description="Whether this event is from a test run"
    )
    test_group: str | None = Field(
        default=None, description="Test group identifier for grouping test events"
    )
    event_metadata: dict[str, Any] | None = Field(
        default=None, description="Arbitrary event metadata to merge"
    )


class StateChangeEventVideo(BaseModel):
    """Presigned video segment associated with a state change event."""

    s3_key: str = Field(..., description="S3 key of the matching video segment")
    url: str = Field(..., description="Presigned URL for the video segment")
    segment_start_time: datetime = Field(
        ..., description="Timestamp parsed from the video filename"
    )
    segment_end_time: datetime = Field(
        ..., description="End timestamp inferred from the segment duration"
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
    videos: list[StateChangeEventVideo] = Field(
        default_factory=list,
        description="Presigned video segments associated with the event",
    )
    video_count: int = Field(
        default=0,
        description="Number of video segments returned",
    )
    event_metadata: dict[str, Any]
    is_test: bool | None = Field(
        default=None, description="Whether this event is from a test run"
    )
    test_group: str | None = Field(
        default=None, description="Test group identifier for grouping test events"
    )


class ListStateChangeEventsResponse(BaseModel):
    """Response for listing state change events."""

    items: list[StateChangeEventResponse]
    total: int
    page: int = 1
    page_size: int = 100
