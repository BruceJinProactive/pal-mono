# Capability Action Change Tracking

**Date**: 2026-03-26
**Author**: Jeffrey Weisinger
**Status**: Implemented

## Context

The change tracking system (audit logs) records create/update/delete operations for various resources across the platform. Prior to this change, it supported:
- Account, Agent, Project
- OrderIntegration, POSIntegration
- SubscriptionPlan, Subscription
- Prompt

Capability actions (the action configurations within agent capabilities) lacked change tracking, making it difficult to:
- Audit who modified action prompts and when
- Track configuration drift over time
- Debug issues related to prompt changes

## Decision

Add `CapabilityAction` as a new resource type to the change tracking enum.

### Implementation Details

**Schema Change (this record):**
```python
class ChangeResourceType(str, enum.Enum):
    # ... existing types ...
    CapabilityAction = "CapabilityAction"  # NEW
```

**Database Impact:**
- **No migration required** - `resource_type` column is `VARCHAR` and already accepts any string value
- Enum is a Python-level constraint only, not enforced at database level
- Existing change_log rows unaffected

**Future Implementation:**
The capability service will be updated to call `create_change_log()` for:
- Creating a capability action
- Updating action fields (prompt, channel, priority, enabled)
- Deleting a capability action

Change logs will reference:
- `account_id` - derived from `CapabilityAction → AgentCapability → Agent → account_id`
- `author` - email from UserContext (admin routes) or `"system"` (public routes)
- `resource_id` - the capability action UUID
- `old_record`/`new_record` - full CapabilityAction model state for diff tracking

## Consequences

### Benefits
- Consistent audit trail for all agent configuration changes
- Aligns with existing change tracking pattern for Prompt resource
- No database migration overhead

### Tradeoffs
- Adds 3 database queries per capability action mutation (fetch capability, agent, create change log)
- Change log volume increases with action configuration updates

## Related
- `db/tables/change_log.py` - enum definition
- `services/capability_service/` - will use this resource type
- `services/history_service/` - provides change tracking infrastructure
