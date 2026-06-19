"""Vision Rule Event API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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
    triggered_at: datetime = Field(description="When the rule was triggered")
    event_metadata: dict[str, Any] = Field(description="Arbitrary event metadata")


class UpdateVisionRuleEventRequest(BaseModel):
    """Request to update editable vision rule event fields."""

    triggered_at: datetime = Field(description="When the rule was triggered")
    duration: Decimal = Field(
        ge=Decimal("0.0"),
        description="Duration of the prior state in minutes",
    )


class ListVisionRuleEventsResponse(BaseModel):
    """Response for listing vision rule events."""

    items: list[VisionRuleEventResponse] = Field(description="List of rule events")
    total: int = Field(description="Total number of events returned")
