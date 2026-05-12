"""Vision Observation API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EntityObservation(BaseModel):
    """Observed state of a single entity."""

    entity_id: uuid.UUID = Field(..., description="ID of the observed entity")
    entity_name: str = Field(..., description="Name of the observed entity")
    camera_id: uuid.UUID = Field(..., description="ID of the camera (signal source)")
    state: str = Field(..., description="Detected state name")
    state_id: uuid.UUID | None = Field(
        default=None, description="ID of the matched state definition"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence score of the observation"
    )


class GenerateObservationResponse(BaseModel):
    """Response from generating an observation."""

    model_config = ConfigDict(from_attributes=True)

    camera_id: uuid.UUID = Field(
        ..., description="ID of the camera (signal source) used for observation"
    )
    observed_at: datetime = Field(..., description="Timestamp of observation")
    entity_observations: list[EntityObservation] = Field(
        ..., description="Observed state for each entity"
    )
    raw_llm_response: dict[str, Any] = Field(
        ..., description="Raw structured output from the LLM"
    )
    token_usage: dict[str, Any] = Field(
        default_factory=dict, description="LLM token usage statistics"
    )
