"""Vision Camera Configuration API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class UpdateCameraConfigRequest(BaseModel):
    """Request to update a vision camera configuration."""

    name: str | None = Field(
        default=None, min_length=1, max_length=255, description="Configuration name"
    )
    llm_prompt: str | None = Field(
        default=None, min_length=1, description="LLM prompt for vision analysis"
    )
    llm_provider: str | None = Field(
        default=None,
        min_length=1,
        max_length=20,
        description="LLM provider (e.g. azure, openai)",
    )
    llm_model: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="LLM model name (e.g. gpt-4o)",
    )
    processing_interval_seconds: int | None = Field(
        default=None, ge=1, description="Seconds between processing frames"
    )
    reference_images: list[Any] | None = Field(
        default=None, description="Reference images for comparison"
    )
    enabled: bool | None = Field(
        default=None, description="Whether the configuration is active"
    )


class CreateCameraConfigRequest(BaseModel):
    """Request to create a vision camera configuration."""

    signal_source_id: uuid.UUID = Field(
        ..., description="Signal source this config is for"
    )
    name: str = Field(
        ..., min_length=1, max_length=255, description="Configuration name"
    )
    llm_prompt: str = Field(
        ..., min_length=1, description="LLM prompt for vision analysis"
    )
    llm_provider: str = Field(
        default="azure",
        min_length=1,
        max_length=20,
        description="LLM provider (e.g. azure, openai)",
    )
    llm_model: str = Field(
        default="gpt-4o",
        min_length=1,
        max_length=100,
        description="LLM model name (e.g. gpt-4o)",
    )
    processing_interval_seconds: int = Field(
        default=15, ge=1, description="Seconds between processing frames"
    )
    reference_images: list[Any] = Field(
        default_factory=list, description="Reference images for comparison"
    )
    enabled: bool = Field(
        default=True, description="Whether the configuration is active"
    )


class CameraConfigResponse(BaseModel):
    """Response model for a vision camera configuration."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    signal_source_id: uuid.UUID
    project_id: uuid.UUID
    name: str
    llm_prompt: str
    llm_provider: str
    llm_model: str
    processing_interval_seconds: int
    reference_images: list[Any]
    enabled: bool
    created_at: datetime
    updated_at: datetime | None


class ListCameraConfigsResponse(BaseModel):
    """Response for listing camera configurations."""

    items: list[CameraConfigResponse]
    total: int


class AssignEntityRequest(BaseModel):
    """Request to assign an entity to a camera configuration."""

    entity_id: uuid.UUID = Field(..., description="Entity to assign")
    roi_hint: dict[str, Any] | None = Field(
        default=None,
        description="Region-of-interest hint for the entity in this camera",
    )


class UpdateCameraEntityRequest(BaseModel):
    """Request to update a camera-entity mapping."""

    roi_hint: dict[str, Any] | None = Field(
        default=None, description="Updated ROI hint"
    )


class CameraEntityResponse(BaseModel):
    """Response model for a camera-entity mapping."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    camera_config_id: uuid.UUID
    entity_id: uuid.UUID
    roi_hint: dict[str, Any] | None
    created_at: datetime


class ListCameraEntitiesResponse(BaseModel):
    """Response for listing camera-entity mappings."""

    items: list[CameraEntityResponse]
    total: int
