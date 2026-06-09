"""Vision Rule API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CreateVisionRuleRequest(BaseModel):
    """Request to create a vision rule."""

    project_id: uuid.UUID = Field(..., description="Project the rule belongs to")
    name: str = Field(..., description="Rule name")
    description: str | None = Field(default=None, description="Rule description")
    type: str = Field(..., description="Rule type")
    severity: str = Field(..., description="Rule severity level")
    is_active: bool = Field(default=True, description="Whether the rule is active")
    rule_metadata: dict[str, Any] = Field(
        default_factory=dict, description="Arbitrary rule metadata"
    )
    label: list[str] = Field(
        default_factory=list, description="Labels associated with the rule"
    )


class UpdateVisionRuleRequest(BaseModel):
    """Request to update a vision rule."""

    name: str | None = Field(default=None, description="Rule name")
    description: str | None = Field(default=None, description="Rule description")
    severity: str | None = Field(default=None, description="Rule severity level")
    is_active: bool | None = Field(
        default=None, description="Whether the rule is active"
    )
    rule_metadata: dict[str, Any] | None = Field(
        default=None, description="Rule metadata to merge"
    )
    label: list[str] | None = Field(
        default=None, description="Labels to replace the existing rule labels"
    )


class VisionRuleResponse(BaseModel):
    """Response model for a vision rule."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Unique identifier for the rule")
    project_id: uuid.UUID = Field(description="Project the rule belongs to")
    name: str = Field(description="Rule name")
    description: str | None = Field(description="Rule description")
    type: str = Field(description="Rule type")
    severity: str = Field(description="Rule severity level")
    is_active: bool = Field(description="Whether the rule is active")
    rule_metadata: dict[str, Any] = Field(description="Arbitrary rule metadata")
    label: list[str] = Field(
        default_factory=list, description="Labels associated with the rule"
    )
    created_at: datetime | None = Field(description="Creation timestamp")
    updated_at: datetime | None = Field(description="Last update timestamp")


class ListVisionRulesResponse(BaseModel):
    """Response for listing vision rules."""

    items: list[VisionRuleResponse] = Field(description="List of vision rules")
    total: int = Field(description="Total number of rules returned")
    items_by_label: dict[str, list[VisionRuleResponse]] = Field(
        default_factory=dict,
        description="Vision rules grouped by label; unlabeled rules use no-labeld",
    )
