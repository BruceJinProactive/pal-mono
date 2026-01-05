"""Monitoring API schemas.

Defines Pydantic models for monitoring configuration validation
and API request/response schemas.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# ============================================================================
# RULES SCHEMAS
# ============================================================================


class ReferenceImage(BaseModel):
    """Reference image with description and unique identifier."""

    id: str = Field(..., description="Unique UUID identifier for this image")
    url: str = Field(..., description="S3 URL/key of the reference image")
    description: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Description of what this reference image represents",
    )


class AIAnalysisRules(BaseModel):
    """Configuration for AI-based analysis rules."""

    prompt: str = Field(
        ..., min_length=1, max_length=2000, description="AI analysis prompt"
    )
    reference_images: list[ReferenceImage] = Field(
        default_factory=list, description="Reference images with descriptions"
    )


# MonitoringRules type alias
MonitoringRules = AIAnalysisRules


# ============================================================================
# API REQUEST/RESPONSE SCHEMAS
# ============================================================================


class CreateMonitoringConfigRequest(BaseModel):
    """Request to create a new monitoring configuration."""

    signal_source_id: uuid.UUID = Field(..., description="Signal source UUID")
    name: str = Field(
        ..., min_length=1, max_length=255, description="Configuration name"
    )
    description: str | None = Field(
        None, max_length=2000, description="Optional description"
    )
    rules: MonitoringRules = Field(..., description="Monitoring rules")
    enabled: bool = Field(True, description="Whether monitoring is enabled")


class UpdateMonitoringConfigRequest(BaseModel):
    """Request to update a monitoring configuration.

    Note: This model is used internally. The actual API endpoint accepts
    multipart/form-data with Form fields for text and File fields for images.
    """

    name: str | None = Field(
        None, min_length=1, max_length=255, description="Updated name"
    )
    description: str | None = Field(
        None, max_length=2000, description="Updated description"
    )
    prompt: str | None = Field(
        None, min_length=1, max_length=2000, description="Updated AI analysis prompt"
    )
    enabled: bool | None = Field(None, description="Updated enabled status")


class ReplaceReferenceImageMapping(BaseModel):
    """Mapping for replacing a specific reference image by ID."""

    image_id: str = Field(..., description="UUID of the image to replace")
    description: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Description for the replacement image",
    )


class UpdateMonitoringConfigImageOperations(BaseModel):
    """Image operations for updating monitoring configuration (documentation only)."""

    remove_image_ids: list[str] = Field(
        default_factory=list,
        description="UUIDs of reference images to remove",
    )
    remove_all_reference_images: bool = Field(
        False, description="Remove all existing reference images"
    )
    replace_all_reference_images: bool = Field(
        False,
        description="Replace all existing images with new ones (requires new images)",
    )


class MonitoringConfigResponse(BaseModel):
    """Response model for a monitoring configuration."""

    id: uuid.UUID
    project_id: uuid.UUID
    signal_source_id: uuid.UUID
    name: str
    description: str | None
    rules: dict
    enabled: bool
    created_at: datetime
    updated_at: datetime | None


class ListMonitoringConfigsResponse(BaseModel):
    """Response for listing monitoring configurations."""

    configs: list[MonitoringConfigResponse]
    total: int
    total_pages: int
    page: int = 1
    page_size: int = 10


class TriggerRunRequest(BaseModel):
    """Request to trigger a manual monitoring run."""

    s3_bucket: str | None = Field(None, description="S3 bucket for image source")
    s3_key: str | None = Field(None, description="S3 key for image source")


class TriggerRunResponse(BaseModel):
    """Response for triggered monitoring run."""

    run_id: uuid.UUID
    monitoring_config_id: uuid.UUID
    status: Literal["processing"]
    message: str


class MonitoringRunResponse(BaseModel):
    """Response model for a monitoring run."""

    id: uuid.UUID
    monitoring_config_id: uuid.UUID
    trigger_metadata: dict
    started_at: datetime
    completed_at: datetime | None
    evaluation_result: dict
    error_message: str | None


class ListMonitoringRunsResponse(BaseModel):
    """Response for listing monitoring runs."""

    runs: list[MonitoringRunResponse]
    total: int
    total_pages: int
    page: int = 1
    page_size: int = 10


class BatchDeleteMonitoringRunsRequest(BaseModel):
    """Request to delete multiple monitoring runs."""

    run_ids: list[uuid.UUID] = Field(
        ..., min_length=1, description="List of run UUIDs to delete"
    )


class BatchDeleteMonitoringRunsResponse(BaseModel):
    """Response for batch delete operation."""

    deleted: int = Field(..., description="Number of runs successfully deleted")
    not_found: int = Field(..., description="Number of runs not found")
    unauthorized: int = Field(
        ..., description="Number of runs user is not authorized to delete"
    )
    message: str = Field(..., description="Summary message")
