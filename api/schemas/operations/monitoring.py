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
    """Reference image with description, unique identifier, and pass/fail flag."""

    id: str = Field(..., description="Unique UUID identifier for this image")
    url: str = Field(..., description="S3 URL/key of the reference image")
    description: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Description of what this reference image represents",
    )
    flag: Literal["pass", "fail"] = Field(
        default="pass",
        description="Whether this image represents a pass or fail example",
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
    """Configuration for AI-based analysis rules.

    Supports both legacy 'prompt' field and new 'context' field.
    During transition, 'prompt' is accepted as an alias for 'context'.
    """

    context: str | None = Field(
        None,
        min_length=1,
        max_length=2000,
        description="Scene/context description for the monitoring analysis",
    )
    prompt: str | None = Field(
        None,
        min_length=1,
        max_length=2000,
        description="Legacy AI analysis prompt (use 'context' for new configs)",
    )
    pass_criteria: list[str] = Field(
        default_factory=list,
        description="List of conditions that indicate a pass result (>= 1 required for new configs)",
    )
    fail_criteria: list[str] = Field(
        default_factory=list,
        description="List of conditions that indicate a fail result (>= 1 required for new configs)",
    )
    reference_images: list[ReferenceImage] = Field(
        default_factory=list,
        description="Optional reference images with descriptions and pass/fail flags",
    )
    structured_output: list[StructuredOutputField] | None = Field(
        None,
        description="Field definitions for structured output. If not provided, uses default {result: 'pass'|'fail'|'error', details: string}",
    )
    monitoring_time_window: MonitoringTimeWindow | None = Field(
        None,
        description="Optional time window configuration to restrict when monitoring runs execute",
    )

    @model_validator(mode="after")
    def validate_context_or_prompt(self) -> "AIAnalysisRules":
        """Ensure at least one of context or prompt is provided."""
        if not self.context and not self.prompt:
            raise ValueError("Either 'context' or 'prompt' must be provided")
        # If only prompt is provided (legacy), use it as context
        if self.prompt and not self.context:
            self.context = self.prompt
        return self

    @field_validator("context", "prompt", mode="before")
    @classmethod
    def strip_and_validate_text_fields(cls, v: str | None) -> str | None:
        """Strip whitespace and reject whitespace-only strings."""
        if v is None:
            return v
        stripped = v.strip()
        if not stripped:
            raise ValueError("Field must contain non-whitespace content")
        return stripped

    @field_validator("pass_criteria", "fail_criteria")
    @classmethod
    def validate_criteria_items(cls, v: list[str]) -> list[str]:
        """Validate individual criteria items: strip whitespace, check length limits."""
        stripped = []
        for item in v:
            s = item.strip()
            if len(s) < 1:
                raise ValueError("Each criterion must be at least 1 character")
            if len(s) > 500:
                raise ValueError(
                    f"Each criterion must be at most 500 characters, got {len(s)}"
                )
            stripped.append(s)
        return stripped


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
    tags: list[str] = Field(
        default_factory=list,
        description="Tags for grouping configs (e.g. 'Food consistency', 'Wait time')",
    )

    @field_validator("tags")
    @classmethod
    def strip_tags(cls, v: list[str]) -> list[str]:
        """Strip leading/trailing whitespace from each tag."""
        return [t.strip() for t in v]


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
    context: str | None = Field(
        None,
        min_length=1,
        max_length=2000,
        description="Updated scene/context description (replaces 'prompt')",
    )
    prompt: str | None = Field(
        None,
        min_length=1,
        max_length=2000,
        description="Legacy: Updated AI analysis prompt (use 'context' instead)",
    )
    pass_criteria: list[str] | None = Field(
        None,
        description="Updated list of conditions that indicate a pass result",
    )
    fail_criteria: list[str] | None = Field(
        None,
        description="Updated list of conditions that indicate a fail result",
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
    tags: list[str] | None = Field(
        None,
        description="Updated tags list. Pass [] to clear all tags. Omit to leave unchanged.",
    )

    @field_validator("tags")
    @classmethod
    def strip_tags(cls, v: list[str] | None) -> list[str] | None:
        """Strip leading/trailing whitespace from each tag."""
        if v is None:
            return v
        return [t.strip() for t in v]

    @field_validator("context", "prompt", mode="before")
    @classmethod
    def strip_and_validate_text_fields(cls, v: str | None) -> str | None:
        """Strip whitespace and reject whitespace-only strings."""
        if v is None:
            return v
        stripped = v.strip()
        if not stripped:
            raise ValueError("Field must contain non-whitespace content")
        return stripped

    @field_validator("pass_criteria", "fail_criteria")
    @classmethod
    def validate_criteria_items(cls, v: list[str] | None) -> list[str] | None:
        """Validate individual criteria items: strip whitespace, check length limits."""
        if v is None:
            return v
        stripped = []
        for item in v:
            s = item.strip()
            if len(s) < 1:
                raise ValueError("Each criterion must be at least 1 character")
            if len(s) > 500:
                raise ValueError(
                    f"Each criterion must be at most 500 characters, got {len(s)}"
                )
            stripped.append(s)
        return stripped


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
    tags: list[str]
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


class TestMonitoringConfigResponse(BaseModel):
    """Response from testing a monitoring configuration.

    Mirrors the structure of actual monitoring run data to preview what will be saved.
    Includes both the prompt sent to LLM and the evaluation result that would be stored.

    Supports both image and video monitoring configurations:
    - Image configs: Uses uploaded test image or latest feed image
    - Video configs: Uses latest captured video from feed (uploaded test videos not supported)
    """

    evaluation_result: dict = Field(
        ...,
        description="The evaluation result that would be saved to the database (result, details, confidence, etc.)",
    )
    error_message: str | None = Field(
        None,
        description="Error message if analysis failed (extracted from evaluation_result when result='error')",
    )
    prompt_sent: dict = Field(
        ...,
        description="The prompt that was sent to the LLM including system instruction, analysis task, and reference images/video structure",
    )
    test_image_url: str | None = Field(
        None,
        description="S3 key/path of the analyzed media (image or video). Null for uploaded test images. For video configs, always contains the S3 video path.",
    )
    test_image_source: str = Field(
        ...,
        description="Source of the test media: 'uploaded test image' for user image uploads, or S3 path for feed images/videos",
    )


class RerunMonitoringRunResponse(BaseModel):
    """Response for rerunning a monitoring run."""

    run_id: uuid.UUID
    monitoring_config_id: uuid.UUID
    status: Literal["processing"]
    message: str


# ============================================================================
# MONITORING SUMMARY SCHEMAS
# ============================================================================


class TagSummary(BaseModel):
    """Aggregated monitoring health for a single tag."""

    tag: str = Field(..., description="Tag name from monitoring configs")
    total_runs: int = Field(..., description="Total monitoring runs in the time range")
    pass_count: int = Field(..., description="Number of runs with pass result")
    fail_count: int = Field(..., description="Number of runs with fail result")
    error_count: int = Field(..., description="Number of runs with error result")
    fail_rate: float = Field(
        ..., description="Ratio of fail runs to total runs (0.0 to 1.0)"
    )


class MonitoringSummaryResponse(BaseModel):
    """Monitoring health summary for a project, grouped by tags.

    Powers the dashboard location card showing per-tag health statuses.
    """

    project_id: uuid.UUID = Field(..., description="Project UUID")
    project_name: str = Field(..., description="Project display name for the card")
    total_tags: int = Field(
        ..., description="Number of unique tags (standards) detected"
    )
    start_date: datetime | None = Field(
        None, description="Start of queried time range (null if unbounded)"
    )
    end_date: datetime | None = Field(
        None, description="End of queried time range (null if unbounded)"
    )
    tags: list[TagSummary] = Field(
        ..., description="Per-tag health summaries sorted by fail count descending"
    )
