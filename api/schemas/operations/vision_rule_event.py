"""Vision Rule Event API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from services.vision_event_service.limits import (
    RULE_EVENT_VIDEO_LOOKUP_MAX_DURATION_MINUTES,
)


class VisionRuleEventResponse(BaseModel):
    """Response model for a vision rule event."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Unique identifier for the rule event")
    rule_id: uuid.UUID = Field(description="Rule that was triggered")
    entity_id: uuid.UUID = Field(description="Entity that triggered the rule")
    state_change_event_id: uuid.UUID = Field(
        description="State change event that caused the trigger"
    )
    severity: str = Field(description="Severity level of the triggered rule")
    duration: Decimal = Field(
        default=Decimal("0.0"),
        description="Duration of the prior state in minutes",
    )
    manually_adjusted: bool = Field(
        default=False,
        description="Whether the rule event was manually added or corrected",
    )
    triggered_at: datetime = Field(description="When the rule was triggered")
    event_metadata: dict[str, Any] = Field(description="Arbitrary event metadata")


class VisionRuleEventVideo(BaseModel):
    """Presigned video segment associated with a rule event."""

    s3_key: str = Field(description="S3 key of the matching video segment")
    url: str = Field(description="Presigned URL for the video segment")
    segment_start_time: datetime = Field(
        description="Timestamp parsed from the video filename"
    )
    segment_end_time: datetime = Field(
        description="End timestamp inferred from the segment duration"
    )


class VisionRuleEventVideoLookupResponse(BaseModel):
    """Response for looking up videos associated with a rule event."""

    rule_event_id: uuid.UUID = Field(description="Rule event used for lookup")
    state_change_event_id: uuid.UUID = Field(
        description="State change event linked to the rule event"
    )
    videos: list[VisionRuleEventVideo] = Field(
        default_factory=list,
        description="Presigned video segments associated with the rule event",
    )
    video_count: int = Field(description="Number of video segments returned")


class UpdateVisionRuleEventRequest(BaseModel):
    """Request to update editable vision rule event fields."""

    triggered_at: datetime = Field(description="When the rule was triggered")
    duration: Decimal = Field(
        ge=Decimal("0.0"),
        le=RULE_EVENT_VIDEO_LOOKUP_MAX_DURATION_MINUTES,
        description=(
            "Duration of the prior state in minutes; must stay within the "
            "video lookup product limit"
        ),
    )
    manually_adjusted: bool = Field(
        default=True,
        description="Whether this update should mark the event as manually adjusted",
    )


class ListVisionRuleEventsResponse(BaseModel):
    """Response for listing vision rule events."""

    items: list[VisionRuleEventResponse] = Field(description="List of rule events")
    total: int = Field(description="Total number of events returned")
