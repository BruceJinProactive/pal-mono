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


class TestEventInfo(BaseModel):
    """A test event associated with this configuration."""

    id: uuid.UUID = Field(..., description="Event ID")
    entity_id: uuid.UUID = Field(..., description="Entity that changed state")
    entity_name: str | None = Field(
        default=None, description="Name of the entity that changed state"
    )
    new_state_id: uuid.UUID = Field(..., description="New state definition ID")
    new_state_name: str | None = Field(
        default=None, description="Name of the new state"
    )
    observed_at: datetime = Field(..., description="When the event was observed")
    confidence: float | None = Field(default=None, description="Confidence score")
    test_group: str | None = Field(
        default=None, description="Test group this event belongs to"
    )
    frame_url: str | None = Field(
        default=None, description="Presigned URL for the frame that triggered the event"
    )


class TestGroupSummary(BaseModel):
    """Test events grouped by test_group."""

    test_group: str | None = Field(
        default=None, description="Test group identifier (None for ungrouped)"
    )
    events: list[TestEventInfo] = Field(
        default_factory=list, description="Events in this test group"
    )


class EntityRoiInfo(BaseModel):
    """ROI hint for an entity in the camera configuration."""

    entity_name: str = Field(..., description="Name of the entity")
    roi_hint: dict[str, Any] | None = Field(
        default=None, description="ROI coordinates (x, y, width, height)"
    )


class ConfigurationPromptResponse(BaseModel):
    """Response containing the full system prompt for a camera configuration."""

    model_config = ConfigDict(from_attributes=True)

    config_id: uuid.UUID = Field(..., description="ID of the camera configuration")
    llm_provider: str = Field(..., description="LLM provider (e.g. azure, google)")
    llm_model: str = Field(..., description="LLM model name (e.g. gpt-4o)")
    system_prompt: str = Field(
        ..., description="Full system prompt that would be sent to the LLM"
    )
    structured_output: dict[str, Any] = Field(
        ..., description="JSON schema for the LLM structured output response format"
    )
    entity_roi_hints: list[EntityRoiInfo] = Field(
        default_factory=list,
        description="ROI hints for each entity in this configuration",
    )
    test_events: list[TestGroupSummary] = Field(
        default_factory=list,
        description="Test events grouped by test_group for this configuration",
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
