"""
Schema definitions for capability service
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

# ============= Agent Capability Schemas =============


class AgentCapabilityBase(BaseModel):
    """Base schema for agent capability"""

    capability_identifier: str = Field(
        ...,
        description="Capability identifier (e.g., 'ordering', 'reservation')",
    )
    priority: int = Field(
        default=50,
        ge=0,
        le=99,
        description="Prompt position (higher = later = stronger)",
    )
    enabled: bool = Field(
        default=True,
        description="Whether this capability is enabled for the agent",
    )


class AgentCapabilityCreate(AgentCapabilityBase):
    """Schema for creating an agent capability"""

    pass


class AgentCapabilityUpdate(BaseModel):
    """Schema for updating an agent capability"""

    priority: Optional[int] = Field(
        None,
        ge=0,
        le=99,
        description="Prompt position (higher = later = stronger)",
    )
    enabled: Optional[bool] = Field(
        None,
        description="Whether this capability is enabled",
    )


class AgentCapabilityResponse(AgentCapabilityBase):
    """Schema for agent capability response"""

    id: UUID
    agent_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============= Capability Action Schemas =============


class ActionBase(BaseModel):
    """Base schema for capability action"""

    action: str = Field(
        ...,
        description="Action name (e.g., 'create_order', 'cancel_order')",
    )
    prompt: str = Field(
        ...,
        description="Custom prompt/instruction for this action",
    )
    channel: str = Field(
        default="ALL",
        description="Channel (SMS, VOICE, EMAIL, ALL)",
        pattern="^(SMS|VOICE|EMAIL|ALL|sms|voice|email|all)$",
    )
    priority: int = Field(
        default=50,
        ge=0,
        le=99,
        description="Prompt position (higher = later = stronger)",
    )
    enabled: bool = Field(
        default=False,
        description="Whether this action is enabled",
    )


class ActionCreate(ActionBase):
    """Schema for creating a capability action"""

    agent_capability_id: UUID = Field(
        ...,
        description="ID of the agent capability this action belongs to",
    )


class ActionUpdate(BaseModel):
    """Schema for updating a capability action"""

    prompt: Optional[str] = Field(
        None,
        description="Custom prompt/instruction for this action",
    )
    channel: Optional[str] = Field(
        None,
        description="Channel (SMS, VOICE, EMAIL, ALL)",
        pattern="^(SMS|VOICE|EMAIL|ALL|sms|voice|email|all)$",
    )
    priority: Optional[int] = Field(
        None,
        ge=0,
        le=99,
        description="Prompt position (higher = later = stronger)",
    )
    enabled: Optional[bool] = Field(
        None,
        description="Whether this action is enabled",
    )


class ActionResponse(ActionBase):
    """Schema for capability action response"""

    id: UUID
    agent_capability_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============= Combined Schemas =============


class CapabilityWithActions(AgentCapabilityResponse):
    """Schema for agent capability with its actions"""

    actions: list[ActionResponse] = Field(
        default_factory=list,
        description="List of actions for this capability",
    )


# ============= Default Capability Schemas =============


class DefaultAction(BaseModel):
    """Schema for a default action from YAML"""

    action: str = Field(
        ...,
        description="Action name (e.g., 'create_order', 'cancel_order')",
    )
    instruction: str = Field(
        ...,
        description="Default instruction/prompt template for this action",
    )
    priority: int = Field(
        ...,
        description="Default priority for action ordering",
    )
    channels: str = Field(
        ...,
        description="Supported channels (ALL, SMS, VOICE, EMAIL)",
    )
    enabled: bool = Field(
        default=True,
        description="Whether this action is enabled by default",
    )


class DefaultCapability(BaseModel):
    """Schema for a default capability from YAML"""

    identifier: str = Field(
        ...,
        description="Capability identifier (e.g., 'ordering', 'reservation')",
    )
    priority: int = Field(
        ...,
        description="Default priority for this capability",
    )
    enabled: bool = Field(
        ...,
        description="Whether this capability is enabled by default",
    )
    description: Optional[str] = Field(
        None,
        description="Description of what this capability does",
    )
    actions: list[DefaultAction] = Field(
        default_factory=list,
        description="List of actions with their default instructions",
    )


class DefaultCapabilitiesResponse(BaseModel):
    """Response containing all available default capabilities"""

    capabilities: list[DefaultCapability] = Field(
        ...,
        description="List of all available default capabilities",
    )


# ============= Bulk Operation Schemas =============


class BulkPriorityUpdate(BaseModel):
    """Schema for bulk priority update"""

    updates: list[tuple[UUID, int]] = Field(
        ...,
        description="List of (capability_id, new_priority) tuples",
    )


class BulkPriorityUpdateResponse(BaseModel):
    """Response for bulk priority update"""

    updated_count: int = Field(
        ...,
        description="Number of capabilities successfully updated",
    )
    requested_count: int = Field(
        ...,
        description="Number of capabilities requested for update",
    )
    success: bool = Field(
        ...,
        description="Whether all requested updates succeeded",
    )
