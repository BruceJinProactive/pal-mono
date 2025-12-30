"""Routine API schemas.

Defines Pydantic models for routine management including routines, items,
schedules, executions, submissions, and item responses.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from db.tables.types import (
    ExecutionStatus,
    ItemResponseStatus,
    RoutineCategory,
    RoutineFrequency,
    RoutineInputType,
    SubmissionStatus,
)

# ============================================================================
# CONFIG SCHEMAS
# ============================================================================


class AIRulesConfig(BaseModel):
    """Configuration for AI-powered photo verification."""

    prompt: str = Field(..., description="Main prompt for AI analysis")
    pass_criteria: list[str] = Field(
        default_factory=list,
        description="Criteria that indicate a passing result",
    )
    fail_criteria: list[str] = Field(
        default_factory=list,
        description="Criteria that indicate a failing result",
    )
    comparison_mode: Literal["reference_match", "checklist"] = Field(
        default="checklist",
        description="How to evaluate: compare to reference image or check criteria list",
    )
    confidence_threshold: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Minimum confidence score to trust AI result",
    )


class ScheduleConfig(BaseModel):
    """Configuration for routine scheduling."""

    frequency: RoutineFrequency = Field(..., description="Frequency of the schedule")
    start_time: str = Field(
        ...,
        pattern=r"^\d{2}:\d{2}$",
        description="Time when routine is due (HH:MM format)",
    )
    end_time: str = Field(
        ...,
        pattern=r"^\d{2}:\d{2}$",
        description="Grace period end time (HH:MM format)",
    )
    timezone: str = Field(
        default="America/Los_Angeles",
        description="Timezone for the schedule",
    )
    days_of_week: list[int] | None = Field(
        default=None,
        description="For weekly: list of days [0=Sun, 1=Mon, ..., 6=Sat]",
    )
    day_of_month: int | None = Field(
        default=None,
        ge=1,
        le=31,
        description="For monthly: day of month (1-31)",
    )
    interval_hours: int | None = Field(
        default=None,
        ge=1,
        le=24,
        description="For custom: hours between executions",
    )
    effective_from: date | None = Field(
        default=None,
        description="Start date for the schedule",
    )
    effective_until: date | None = Field(
        default=None,
        description="End date for the schedule",
    )

    @model_validator(mode="after")
    def validate_frequency_fields(self):
        """Validate that frequency-specific fields are provided."""
        if self.frequency == RoutineFrequency.weekly and not self.days_of_week:
            raise ValueError("days_of_week required for weekly frequency")
        if self.frequency == RoutineFrequency.monthly and not self.day_of_month:
            raise ValueError("day_of_month required for monthly frequency")
        if self.frequency == RoutineFrequency.custom and not self.interval_hours:
            raise ValueError("interval_hours required for custom frequency")
        return self


# ============================================================================
# ROUTINE ITEM SCHEMAS
# ============================================================================


class CreateRoutineItemRequest(BaseModel):
    """Request to create a routine item."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Name of the item",
    )
    description: str | None = Field(
        default=None,
        description="Optional description",
    )
    sort_order: int | None = Field(
        default=None,
        ge=0,
        description="Order in the routine (auto-assigned if not provided)",
    )
    input_type: RoutineInputType = Field(
        default=RoutineInputType.photo,
        description="Type of input (V1: photo only)",
    )
    is_required: bool = Field(
        default=True,
        description="Whether the item is required",
    )
    ai_rules: AIRulesConfig | None = Field(
        default=None,
        description="AI verification rules",
    )
    signal_source_id: uuid.UUID | None = Field(
        default=None,
        description="Optional camera integration for auto-verify",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Ensure name is not empty."""
        if not v.strip():
            raise ValueError("Name cannot be empty")
        return v.strip()


class UpdateRoutineItemRequest(BaseModel):
    """Request to update a routine item."""

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="New name",
    )
    description: str | None = Field(
        default=None,
        description="New description",
    )
    sort_order: int | None = Field(
        default=None,
        ge=0,
        description="New sort order",
    )
    input_type: RoutineInputType | None = Field(
        default=None,
        description="New input type",
    )
    is_required: bool | None = Field(
        default=None,
        description="New required status",
    )
    ai_rules: AIRulesConfig | None = Field(
        default=None,
        description="New AI rules",
    )
    signal_source_id: uuid.UUID | None = Field(
        default=None,
        description="New signal source ID",
    )


class RoutineItemResponse(BaseModel):
    """Response model for a routine item."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    routine_id: uuid.UUID
    name: str
    description: str | None
    sort_order: int
    input_type: RoutineInputType
    is_required: bool
    reference_image_url: str | None
    ai_rules: dict[str, Any]
    signal_source_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime | None


# ============================================================================
# ROUTINE SCHEMAS
# ============================================================================


class CreateRoutineRequest(BaseModel):
    """Request to create a routine with items and optional schedule."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Name of the routine",
    )
    description: str | None = Field(
        default=None,
        description="Optional description",
    )
    category: RoutineCategory = Field(
        default=RoutineCategory.custom,
        description="Category of the routine",
    )
    items: list[CreateRoutineItemRequest] = Field(
        default_factory=list,
        description="Items to create with the routine",
    )
    schedule: ScheduleConfig | None = Field(
        default=None,
        description="Optional schedule to create with the routine",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Ensure name is not empty."""
        if not v.strip():
            raise ValueError("Name cannot be empty")
        return v.strip()


class UpdateRoutineRequest(BaseModel):
    """Request to update a routine."""

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="New name",
    )
    description: str | None = Field(
        default=None,
        description="New description",
    )
    category: RoutineCategory | None = Field(
        default=None,
        description="New category",
    )
    is_active: bool | None = Field(
        default=None,
        description="New active status",
    )


class RoutineResponse(BaseModel):
    """Response model for a routine (without items)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str | None
    category: RoutineCategory
    is_active: bool
    created_at: datetime
    updated_at: datetime | None


class RoutineDetailResponse(RoutineResponse):
    """Response model for a routine with items."""

    items: list[RoutineItemResponse] = Field(default_factory=list)


class ListRoutinesResponse(BaseModel):
    """Response for listing routines."""

    routines: list[RoutineResponse]
    total: int


# ============================================================================
# SCHEDULE SCHEMAS
# ============================================================================


class CreateScheduleRequest(ScheduleConfig):
    """Request to create a schedule.

    Inherits all fields and validation from ScheduleConfig.
    """

    pass


class UpdateScheduleRequest(BaseModel):
    """Request to update a schedule."""

    frequency: RoutineFrequency | None = Field(default=None)
    start_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    end_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    timezone: str | None = Field(default=None)
    days_of_week: list[int] | None = Field(default=None)
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    interval_hours: int | None = Field(default=None, ge=1, le=24)
    effective_from: date | None = Field(default=None)
    effective_until: date | None = Field(default=None)
    is_active: bool | None = Field(default=None)

    @model_validator(mode="after")
    def validate_frequency_fields(self):
        """Validate frequency-specific fields when frequency is being updated."""
        # Only validate if frequency is being explicitly updated
        if self.frequency is None:
            return self

        if self.frequency == RoutineFrequency.weekly and not self.days_of_week:
            raise ValueError("days_of_week required when updating frequency to weekly")
        if self.frequency == RoutineFrequency.monthly and not self.day_of_month:
            raise ValueError("day_of_month required when updating frequency to monthly")
        if self.frequency == RoutineFrequency.custom and not self.interval_hours:
            raise ValueError(
                "interval_hours required when updating frequency to custom"
            )
        return self


class ScheduleResponse(BaseModel):
    """Response model for a schedule."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    routine_id: uuid.UUID
    frequency: RoutineFrequency
    start_time: time
    end_time: time
    timezone: str
    days_of_week: list[int] | None
    day_of_month: int | None
    interval_hours: int | None
    effective_from: date | None
    effective_until: date | None
    is_active: bool
    created_at: datetime
    updated_at: datetime | None


class ListSchedulesResponse(BaseModel):
    """Response for listing schedules."""

    schedules: list[ScheduleResponse]
    total: int


# ============================================================================
# EXECUTION SCHEMAS
# ============================================================================


class ExecutionResponse(BaseModel):
    """Response model for an execution."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    routine_id: uuid.UUID
    schedule_id: uuid.UUID
    scheduled_start: datetime
    scheduled_end: datetime
    status: ExecutionStatus
    assigned_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime | None


class ExecutionDetailResponse(ExecutionResponse):
    """Response model for an execution with routine info."""

    routine_name: str | None = None
    has_submission: bool = False


class ListExecutionsResponse(BaseModel):
    """Response for listing executions."""

    executions: list[ExecutionDetailResponse]
    total: int


# ============================================================================
# ITEM RESPONSE SCHEMAS
# ============================================================================


class AddResponseRequest(BaseModel):
    """Request to add a response to a submission item.

    Note: The actual image is uploaded via multipart/form-data.
    """

    routine_item_id: uuid.UUID = Field(
        ...,
        description="ID of the routine item being responded to",
    )
    notes: str | None = Field(
        default=None,
        description="Staff notes/comments",
    )


class ItemResponseResponse(BaseModel):
    """Response model for an item response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    submission_id: uuid.UUID
    routine_item_id: uuid.UUID
    image_url: str | None
    notes: str | None
    ai_result: dict[str, Any] | None
    ai_passed: bool | None
    ai_confidence: Decimal | None
    status: ItemResponseStatus
    created_at: datetime
    updated_at: datetime | None


class ItemResponseWithItemResponse(ItemResponseResponse):
    """Response model for an item response with item details."""

    item_name: str | None = None
    item_description: str | None = None
    is_required: bool = True


# ============================================================================
# SUBMISSION SCHEMAS
# ============================================================================


class SubmissionResponse(BaseModel):
    """Response model for a submission (without responses)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    execution_id: uuid.UUID
    status: SubmissionStatus
    submitted_by: uuid.UUID | None
    submitted_at: datetime | None
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    review_notes: str | None
    created_at: datetime
    updated_at: datetime | None


class SubmissionDetailResponse(SubmissionResponse):
    """Response model for a submission with responses."""

    responses: list[ItemResponseWithItemResponse] = Field(default_factory=list)
    routine_name: str | None = None


class RejectSubmissionRequest(BaseModel):
    """Request to reject a submission."""

    review_notes: str = Field(
        ...,
        min_length=1,
        description="Reason for rejection",
    )


class ListPendingReviewResponse(BaseModel):
    """Response for listing submissions pending review."""

    submissions: list[SubmissionDetailResponse]
    total: int
