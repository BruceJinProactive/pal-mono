"""Monitoring API schemas.

Defines Pydantic models for monitoring configuration validation
and API request/response schemas.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, model_validator

# ============================================================================
# RULES SCHEMAS
# ============================================================================


class AIAnalysisRules(BaseModel):
    """Configuration for AI-based analysis rules."""

    type: Literal["ai_analysis"] = "ai_analysis"

    prompt: str = Field(
        ..., min_length=1, max_length=2000, description="AI analysis prompt"
    )
    reference_image_urls: list[str] = Field(
        default_factory=list, description="S3 URLs of reference images"
    )
    comparison_mode: Literal["best_match", "all_match"] = Field(
        "best_match", description="How to compare against references"
    )
    confidence_threshold: float = Field(
        0.8, ge=0.0, le=1.0, description="Minimum confidence for pass"
    )


class ThresholdRules(BaseModel):
    """Configuration for threshold-based rules."""

    type: Literal["threshold"] = "threshold"

    metric: str = Field(..., description="Name of metric to check")
    operator: Literal["lt", "gt", "lte", "gte", "eq", "between"] = Field(
        ..., description="Comparison operator"
    )
    value: float | None = Field(None, description="Value for single-value operators")
    min: float | None = Field(None, description="Minimum value for 'between' operator")
    max: float | None = Field(None, description="Maximum value for 'between' operator")
    unit: str | None = Field(None, description="Unit of measurement")

    @model_validator(mode="after")
    def validate_threshold_fields(self) -> "ThresholdRules":
        """Validate that correct fields are provided based on operator."""
        if self.operator == "between":
            # For 'between', require min and max
            if self.min is None or self.max is None:
                raise ValueError(
                    "Operator 'between' requires both 'min' and 'max' fields"
                )
            if self.value is not None:
                raise ValueError("Operator 'between' should not have 'value' field")
            # Ensure min < max
            if self.min >= self.max:
                raise ValueError(
                    f"'min' ({self.min}) must be less than 'max' ({self.max})"
                )
        else:
            # For single-value operators, require value
            if self.value is None:
                raise ValueError(f"Operator '{self.operator}' requires 'value' field")
            if self.min is not None or self.max is not None:
                raise ValueError(
                    f"Operator '{self.operator}' should not have 'min' or 'max' fields"
                )

        return self


# Discriminated union for rule types
MonitoringRules = Annotated[
    Union[AIAnalysisRules, ThresholdRules],
    Field(discriminator="type"),
]


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
