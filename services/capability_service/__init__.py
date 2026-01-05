"""
Capability Service - Manages agent capabilities and actions

This service provides business logic for managing agent-specific capability
configurations and action overrides.
"""

from . import _implementation as impl
from .schema import (
    ActionCreate,
    ActionResponse,
    ActionUpdate,
    AgentCapabilityCreate,
    AgentCapabilityResponse,
    AgentCapabilityUpdate,
    BulkPriorityUpdate,
    BulkPriorityUpdateResponse,
    CapabilityWithActions,
    DefaultAction,
    DefaultCapabilitiesResponse,
    DefaultCapability,
)

__all__ = [
    # Schema exports
    "AgentCapabilityCreate",
    "AgentCapabilityUpdate",
    "AgentCapabilityResponse",
    "ActionCreate",
    "ActionUpdate",
    "ActionResponse",
    "CapabilityWithActions",
    "DefaultAction",
    "DefaultCapability",
    "DefaultCapabilitiesResponse",
    "BulkPriorityUpdate",
    "BulkPriorityUpdateResponse",
    # Service functions
    "get_default_capabilities",
    "create_agent_capability",
    "get_agent_capabilities",
    "update_agent_capability",
    "delete_agent_capability",
    "bulk_update_priorities",
    "create_capability_action",
    "upsert_capability_action",
    "get_capability_actions",
    "update_capability_action",
    "delete_capability_action",
    "get_agent_capabilities_with_actions",
]

# Service function exports
get_default_capabilities = impl.get_default_capabilities

create_agent_capability = impl.create_agent_capability
get_agent_capabilities = impl.get_agent_capabilities
update_agent_capability = impl.update_agent_capability
delete_agent_capability = impl.delete_agent_capability
bulk_update_priorities = impl.bulk_update_priorities

create_capability_action = impl.create_capability_action
upsert_capability_action = impl.upsert_capability_action
get_capability_actions = impl.get_capability_actions
update_capability_action = impl.update_capability_action
delete_capability_action = impl.delete_capability_action

get_agent_capabilities_with_actions = impl.get_agent_capabilities_with_actions
