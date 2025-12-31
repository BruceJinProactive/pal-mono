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
    """Reference image with description."""

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
    """Request to update a monitoring configuration."""

    name: str | None = Field(
        None, min_length=1, max_length=255, description="Updated name"
    )
    description: str | None = Field(
        None, max_length=2000, description="Updated description"
    )
    rules: MonitoringRules | None = Field(None, description="Updated rules")
    enabled: bool | None = Field(None, description="Updated enabled status")


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
