"""Monitoring API schemas.

Defines Pydantic models for monitoring configuration validation
and API request/response schemas.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# ============================================================================
# MONITORING TIME WINDOW SCHEMA
# ============================================================================


class MonitoringTimeWindow(BaseModel):
    """Configuration for monitoring time window.

    When enabled, monitoring runs will only execute during the specified time window.
    Times are in HH:MM 24-hour format and interpreted in the store's timezone.

    Supports overnight windows (e.g., 22:00-02:00 for late-night venues).
    """

    enabled: bool = Field(
        default=False,
        description="Whether to restrict monitoring to the specified time window",
    )
    start_time: str | None = Field(
        default=None,
        pattern=r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$",
        description="Start time in HH:MM 24-hour format (e.g., '06:00', '22:00')",
    )
    end_time: str | None = Field(
        default=None,
        pattern=r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$",
        description="End time in HH:MM 24-hour format (e.g., '22:00', '02:00')",
    )

    @model_validator(mode="after")
    def validate_times_when_enabled(self) -> "MonitoringTimeWindow":
        """Validate that start_time and end_time are provided when enabled."""
        if self.enabled:
            if not self.start_time or not self.end_time:
                raise ValueError(
                    "Both start_time and end_time are required when time window is enabled"
                )
        return self


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


class EnumMetadata(BaseModel):
    """Metadata for a single enum value (description and UI color)."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Enum value name (must match a value in enum_values)",
    )
    description: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Human-readable description of this enum value",
    )
    color: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Tailwind CSS classes for UI display (e.g., 'bg-green-100 text-green-800')",
    )


class StructuredOutputField(BaseModel):
    """Field definition for structured output schema."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=50,
        pattern="^[a-zA-Z_][a-zA-Z0-9_]*$",
        description="Field name (snake_case)",
    )
    description: str = Field(
        ..., min_length=1, max_length=1000, description="What this field represents"
    )
    required: bool = Field(True, description="Whether field is required")
    enum_values: list[str] | None = Field(
        None,
        description="Allowed values (optional, restricts field to specific options)",
    )
    enum_metadata: list[EnumMetadata] | None = Field(
        None,
        description="Metadata for each enum value (description and color for UI display)",
    )

    @field_validator("enum_metadata")
    @classmethod
    def validate_enum_metadata(
        cls, v: list[EnumMetadata] | None, info
    ) -> list[EnumMetadata] | None:
        """Validate that enum_metadata names match enum_values."""
        if v is None:
            return v

        # Get enum_values from the field data
        enum_values = info.data.get("enum_values")

        # If enum_metadata is provided but enum_values is not, raise error
        if enum_values is None:
            raise ValueError(
                "enum_metadata requires enum_values to be specified. "
                "Please provide enum_values list."
            )

        # Check that all enum_metadata names exist in enum_values
        enum_value_set = set(enum_values)
        metadata_names = [meta.name for meta in v]

        invalid_names = [name for name in metadata_names if name not in enum_value_set]
        if invalid_names:
            raise ValueError(
                f"enum_metadata contains names not in enum_values: {invalid_names}. "
                f"Valid values are: {enum_values}"
            )

        # Check for duplicate names in metadata
        if len(metadata_names) != len(set(metadata_names)):
            duplicates = [
                name for name in metadata_names if metadata_names.count(name) > 1
            ]
            raise ValueError(
                f"enum_metadata contains duplicate names: {set(duplicates)}"
            )

        return v


class AIAnalysisRules(BaseModel):
    """Configuration for AI-based analysis rules."""

    prompt: str = Field(
        ..., min_length=1, max_length=2000, description="AI analysis prompt"
    )
    reference_images: list[ReferenceImage] = Field(
        default_factory=list, description="Reference images with descriptions"
    )
    structured_output: list[StructuredOutputField] | None = Field(
        None,
        description="Field definitions for structured output. If not provided, uses default {result: 'pass'|'fail'|'error', details: string}",
    )
    monitoring_time_window: MonitoringTimeWindow | None = Field(
        None,
        description="Optional time window configuration to restrict when monitoring runs execute",
    )


# MonitoringRules type alias
MonitoringRules = AIAnalysisRules


# ============================================================================
# API REQUEST/RESPONSE SCHEMAS
# ============================================================================


class ModelConfig(BaseModel):
    """LLM model configuration for monitoring analysis."""

    provider: str | None = Field(
        None,
        description='LLM provider: "azure" or "google"',
        pattern="^(azure|google)$",
    )
    model: str | None = Field(
        None,
        min_length=1,
        max_length=100,
        description="Model identifier (e.g., 'gpt-4o', 'gemini-3-flash-preview', 'gemini-2.5-flash', 'gemini-2.5-pro')",
    )


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
    model: ModelConfig | None = Field(
        None,
        description="LLM model configuration override (provider and model)",
    )
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
    structured_output: list[StructuredOutputField] | None = Field(
        None,
        description="Updated field definitions for structured output",
    )
    model: ModelConfig | None = Field(
        None,
        description="LLM model configuration override (provider and model)",
    )
    enabled: bool | None = Field(None, description="Updated enabled status")
    monitoring_time_window: MonitoringTimeWindow | None = Field(
        None,
        description="Updated time window configuration to restrict when monitoring runs execute",
    )


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
    """Response model for a monitoring run (detailed view with image URL)."""

    id: uuid.UUID
    monitoring_config_id: uuid.UUID
    image_url: str | None
    started_at: datetime
    completed_at: datetime | None
    evaluation_result: dict
    error_message: str | None


class MonitoringRunListResponse(BaseModel):
    """Response model for a monitoring run in list view (without image URL for performance)."""

    id: uuid.UUID
    monitoring_config_id: uuid.UUID
    started_at: datetime
    completed_at: datetime | None
    evaluation_result: dict
    error_message: str | None


class ListMonitoringRunsResponse(BaseModel):
    """Response for listing monitoring runs."""

    runs: list[MonitoringRunListResponse]


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
