"""Vision Entity API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class UpdateEntityTypeRequest(BaseModel):
    """Request to update a vision entity type."""

    name: str | None = Field(
        default=None, min_length=1, max_length=100, description="Machine-readable name"
    )
    display_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Human-readable label",
    )
    description: str | None = Field(
        default=None, description="Description of the entity type"
    )
    icon: str | None = Field(
        default=None, max_length=10, description="Emoji icon for UI"
    )
    is_active: bool | None = Field(
        default=None, description="Whether the entity type is active"
    )


class CreateEntityTypeRequest(BaseModel):
    """Request to create a vision entity type."""

    name: str = Field(
        ..., min_length=1, max_length=100, description="Machine-readable name"
    )
    display_name: str = Field(
        ..., min_length=1, max_length=255, description="Human-readable label"
    )
    description: str | None = Field(
        default=None, description="Description of the entity type"
    )
    icon: str | None = Field(
        default=None, max_length=10, description="Emoji icon for UI"
    )


class EntityTypeResponse(BaseModel):
    """Response model for a vision entity type."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    name: str
    display_name: str
    description: str | None
    icon: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime | None


class ListEntityTypesResponse(BaseModel):
    """Response for listing entity types."""

    items: list[EntityTypeResponse]
    total: int


# ---------------------------------------------------------------------------
# State Definition schemas
# ---------------------------------------------------------------------------


class UpdateStateDefinitionRequest(BaseModel):
    """Request to update a vision entity state definition."""

    name: str | None = Field(
        default=None, min_length=1, max_length=100, description="Machine-readable name"
    )
    display_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Human-readable label",
    )
    color: str | None = Field(
        default=None, max_length=7, description="Hex color code (e.g. #FF0000)"
    )
    definition_type: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
        description="State definition group, such as cleanliness or occupation",
    )
    sort_order: int | None = Field(default=None, ge=0, description="Display ordering")
    is_default: bool | None = Field(
        default=None, description="Whether this is the default state"
    )
    is_active: bool | None = Field(
        default=None, description="Whether this state definition is active"
    )
    criteria: str | None = Field(
        default=None,
        max_length=500,
        description="Criteria for matching this state",
    )


class CreateStateDefinitionRequest(BaseModel):
    """Request to create a vision entity state definition."""

    name: str = Field(
        ..., min_length=1, max_length=100, description="Machine-readable name"
    )
    display_name: str = Field(
        ..., min_length=1, max_length=255, description="Human-readable label"
    )
    color: str | None = Field(
        default=None, max_length=7, description="Hex color code (e.g. #FF0000)"
    )
    definition_type: str = Field(
        default="cleanliness",
        min_length=1,
        max_length=50,
        description="State definition group, such as cleanliness or occupation",
    )
    sort_order: int = Field(default=0, ge=0, description="Display ordering")
    is_default: bool = Field(
        default=False, description="Whether this is the default state"
    )
    is_active: bool = Field(
        default=True, description="Whether this state definition is active"
    )
    criteria: str | None = Field(
        default=None,
        max_length=500,
        description="Criteria for matching this state",
    )


class StateDefinitionResponse(BaseModel):
    """Response model for a vision entity state definition."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_type_id: uuid.UUID
    name: str
    display_name: str
    color: str | None
    definition_type: str
    sort_order: int
    is_default: bool
    is_active: bool
    criteria: str | None
    created_at: datetime


class ListStateDefinitionsResponse(BaseModel):
    """Response for listing state definitions."""

    items: list[StateDefinitionResponse]
    total: int


# ---------------------------------------------------------------------------
# Entity schemas
# ---------------------------------------------------------------------------


class UpdateEntityRequest(BaseModel):
    """Request to update a vision entity."""

    name: str | None = Field(
        default=None, min_length=1, max_length=255, description="Entity name"
    )
    entity_metadata: dict[str, Any] | None = Field(
        default=None, description="Arbitrary metadata"
    )
    is_active: bool | None = Field(
        default=None, description="Whether the entity is active"
    )


class CreateEntityRequest(BaseModel):
    """Request to create a vision entity."""

    entity_type_id: uuid.UUID = Field(
        ..., description="Entity type this entity belongs to"
    )
    name: str = Field(..., min_length=1, max_length=255, description="Entity name")
    entity_metadata: dict[str, Any] = Field(
        default_factory=dict, description="Arbitrary metadata"
    )


class UpdateEntityStateRequest(BaseModel):
    """Request to transition an entity to a new state."""

    state_definition_id: uuid.UUID = Field(
        ..., description="Target state definition ID"
    )


class EntityCurrentStateResponse(BaseModel):
    """Current state for one state definition type."""

    state_definition_id: uuid.UUID
    state: str | None = None
    current_state_since: datetime | None = None
    observed_at: datetime | None = None


class EntityResponse(BaseModel):
    """Response model for a vision entity."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    entity_type_id: uuid.UUID
    name: str
    current_state_id: uuid.UUID | None
    current_state_since: datetime | None
    current_states: dict[str, EntityCurrentStateResponse] = Field(default_factory=dict)
    entity_metadata: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime | None


class ListEntitiesResponse(BaseModel):
    """Response for listing entities."""

    items: list[EntityResponse]
    total: int
