# PromptV2 Capability-Based Architecture

## Overview

The PromptV2 service is evolving to a database-driven, capability-based prompt management system. This architecture extends the existing `PromptFactoryV2` to support hierarchical organization with Capabilities → Actions → Prompts, enabling granular customization and efficient prompt combination for AI agents.

## Summary: Default Actions and Override Strategy

The system will handle default actions and database overrides as follows:

1. **Default Capabilities in YAML**: Each capability has its own YAML file with default actions and prompts
2. **Database Overrides**: The `capability_actions` table stores only overrides, not defaults
3. **Always-Enabled Capabilities**: Only "general" capability is always-enabled (set via `always_enabled` field in YAML)
4. **Capability Inclusion Logic**:
   - Include if `always_enabled=true` in capabilities YAML
   - Include if agent has it enabled in `agent_capabilities` table
   - Otherwise, exclude from prompt
5. **Priority System**:
   - Capabilities get default priority from YAML file
   - Agent can override priority in `agent_capabilities` table
   - Actions within capabilities have their own priority for ordering
6. **Override Precedence**: Database overrides always take precedence over YAML defaults

## Core Concepts

### Hierarchy
- **Capabilities**: High-level agent abilities (ordering, reservation, waitlist, general)
- **Actions**: Specific operations within capabilities (create_order, cancel_order, make_reservation)
- **Prompts**: Instructional text for each action
- **Customizations**: Agent-specific overrides with fallback to defaults

### Requirements
- Database-driven prompt storage and retrieval
- Agent-level capability enablement and customization
- Priority-based prompt combination for LLM context
- Channel-specific prompt variations (SMS, VOICE, EMAIL)
- Default prompts with customization override capability

## Database Schema (2 Tables)

### 1. Agent_Capabilities Table
```sql
CREATE TABLE agent_capabilities (
    id UUID PRIMARY KEY,
    agent_id UUID REFERENCES agents(id),
    capability_identifier VARCHAR NOT NULL,       -- 'ordering', 'reservation', etc.
    priority INTEGER NOT NULL,          -- Determines combination order
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    UNIQUE(agent_id, capability_identifier)
);
```

### 2. Capability_Actions Table (Overrides Only)
```sql
CREATE TABLE capability_actions (
    id UUID PRIMARY KEY,
    agent_capability_id UUID REFERENCES agent_capabilities(id),
    action VARCHAR NOT NULL,            -- 'create_order', 'cancel_order', etc.
    prompt TEXT NOT NULL,               -- Override prompt (defaults in YAML)
    channel VARCHAR,                    -- NULL for all channels, or specific channel
    priority INTEGER NOT NULL,          -- Order within capability
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    UNIQUE(agent_capability_id, action, channel)
);
```

## PromptFactoryV2 Interface

The `PromptFactoryV2` class will be updated to use the capability-based system with startup caching:

### Core Methods
```python
class PromptFactoryV2:
    # Class-level cache shared across all instances
    _capability_cache = {}  # Could be dict, dataclass, or custom structure
    _is_loaded = False

    def __init__(self):
        """Initialize and cache all capability YAML files at startup (once)"""
        if not PromptFactoryV2._is_loaded:
            self._load_all_capabilities()
            PromptFactoryV2._is_loaded = True

    def _load_all_capabilities(self) -> None:
        """
        Load all capability YAML files at startup into class-level cache.
        Cache structure can be optimized based on access patterns.
        """
        # Implementation will parse YAML files and store in appropriate data structure

    # Main build method using capability system
    def build(self, channel: Channel, agent_id: UUID) -> list[tuple[str, str]]:
        """Build prompts using capability system"""

    # Agent Capability Management (via repositories)
    async def get_agent_capabilities(self, session, agent_id: UUID) -> List[AgentCapability]:
        """Get all capabilities for an agent with their status"""

    async def add_capability_to_agent(self, session, agent_id: UUID, capability_identifier: str,
                                      priority: int = 50) -> AgentCapability:
        """Add a capability to an agent with specified priority"""

    async def update_capability(self, session, agent_capability_id: UUID,
                               enabled: Optional[bool] = None,
                               priority: Optional[int] = None) -> bool:
        """Update a capability's enabled status and/or priority"""

    async def remove_capability_from_agent(self, session, agent_capability_id: UUID) -> bool:
        """Remove a capability from an agent"""

    # Action Management (via repositories)
    async def get_capability_actions(self, session, agent_capability_id: UUID,
                                    channel: Optional[str] = None) -> List[Action]:
        """Get all actions for a capability (defaults + overrides merged)"""

    async def create_action(self, session, agent_capability_id: UUID, action: str,
                          prompt: str, channel: Optional[str] = None,
                          priority: Optional[int] = None) -> Action:
        """Create or update an action override for a capability"""

    async def update_action(self, session, capability_action_id: UUID,
                          prompt: Optional[str] = None,
                          channel: Optional[str] = None,
                          priority: Optional[int] = None) -> bool:
        """Update the prompt, channel, and/or priority of an action override"""

    async def remove_action(self, session, capability_action_id: UUID) -> bool:
        """Remove an action override by ID, reverting to default"""
```

## Default Prompts YAML Structure

The default prompts will be organized in YAML files, one per capability:

### File Structure
```
services/prompt_service/capabilities/
├── ordering.yaml
├── reservation.yaml
├── waitlist.yaml
└── general.yaml
```

### YAML Format Example (ordering.yaml)
```yaml
capability:
  name: ordering
  description: "Handle order creation, modification, and cancellation"
  always_enabled: false  # Default value, can be omitted

actions:
  - name: create_order
    priority: 10  # Default priority (can be overridden in DB)
    channels:  # Optional, if not specified applies to all channels
      - SMS
      - VOICE
    prompt: |
      ## Creating Orders
      When creating an order, follow these guidelines:
      - Confirm all items with the customer
      - Verify pricing and availability
      - Collect delivery/pickup information

  - name: modify_order
    priority: 20
    prompt: |
      ## Modifying Orders
      For order modifications:
      - Verify the original order details
      - Confirm changes with customer

  - name: cancel_order
    priority: 30
    prompt: |
      ## Canceling Orders
      When canceling orders:
      - Verify order identity
      - Explain cancellation policy
```

### General Capability (general.yaml)
```yaml
capability:
  name: general
  description: "Basic store information and FAQs"
  always_enabled: true  # This capability is always included for all agents

actions:
  - name: store_hours
    priority: 100
    prompt: |
      ## Store Hours
      Provide store hours when asked...

  - name: store_address
    priority: 110
    prompt: |
      ## Store Address
      Provide location information...

  - name: answer_faq
    priority: 120
    prompt: |
      ## Frequently Asked Questions
      Handle common questions...
```

## Build Method Implementation Logic

The `build()` method will follow this algorithm:

```python
def build(self, channel: Channel, agent_id: UUID) -> list[tuple[str, str]]:
    """
    Build the combined prompt string with the following logic:

    1. Get all capability YAML files (ordering, reservation, waitlist, general)
    2. For each capability:
       a. Check if it's always_enabled in YAML OR if agent has it enabled in agent_capabilities
       b. If not included, skip this capability

    3. For included capabilities:
       a. Load default actions from YAML file (services/prompt_service/capabilities/{name}.yaml)
       b. Query capability_actions table for any overrides for this agent
       c. Merge actions (database overrides replace YAML defaults)
       d. Filter by channel if specified
       e. Sort actions by priority within capability

    4. Sort all capabilities by their priority (from agent_capabilities or YAML default)

    5. Return list of tuples (title, prompt) for each action
    """

    included_capabilities = []

    # Step 1: Load all capability definitions from YAML files
    capability_files = ['ordering', 'reservation', 'waitlist', 'general']
    all_capabilities = {}
    for cap_name in capability_files:
        cap_config = self._load_capability_config(cap_name)  # Loads YAML config
        all_capabilities[cap_name] = cap_config

    # Step 2: Get agent's enabled capabilities from database
    agent_capabilities = self.get_agent_capabilities(agent_id)
    agent_cap_map = {ac.capability_identifier: ac for ac in agent_capabilities}

    # Step 3: Determine which capabilities to include
    for cap_name, cap_config in all_capabilities.items():
        if cap_config.get('always_enabled', False):
            # Always include with high priority (1) unless agent has explicit override
            if cap_name in agent_cap_map and agent_cap_map[cap_name].priority:
                priority = agent_cap_map[cap_name].priority
            else:
                priority = 1  # High priority for always-enabled capabilities
            included_capabilities.append((cap_name, cap_config, priority))
        elif cap_name in agent_cap_map and agent_cap_map[cap_name].enabled:
            # Include if explicitly enabled for agent
            included_capabilities.append((cap_name, cap_config, agent_cap_map[cap_name].priority))

    # Step 4: Build prompt for each included capability
    prompts = []
    for cap_name, cap_config, cap_priority in sorted(included_capabilities, key=lambda x: x[2]):
        # Get actions from YAML config
        yaml_actions = cap_config.get('actions', [])

        # Get database overrides if agent has this capability
        db_overrides = {}
        if cap_name in agent_cap_map:
            overrides = self._get_action_overrides(agent_cap_map[cap_name].id, channel)
            db_overrides = {o.action: o for o in overrides}

        # Merge and sort actions
        capability_prompts = []
        for yaml_action in yaml_actions:
            action_name = yaml_action['name']
            # Use database override if exists, otherwise use YAML default
            if action_name in db_overrides:
                override = db_overrides[action_name]
                if channel and override.channel and override.channel != channel:
                    continue  # Skip if channel doesn't match
                capability_prompts.append({
                    'name': action_name,
                    'priority': override.priority,
                    'prompt': override.prompt
                })
            else:
                # Use YAML default
                if channel and 'channels' in yaml_action and channel not in yaml_action['channels']:
                    continue  # Skip if channel doesn't match
                capability_prompts.append({
                    'name': action_name,
                    'priority': yaml_action.get('priority', 50),
                    'prompt': yaml_action['prompt']
                })

        # Sort by action priority and add to final list
        for action in sorted(capability_prompts, key=lambda x: x['priority']):
            # Add as tuple with title derived from action name
            prompts.append((f"## {cap_name.title()} - {action['name']}", action['prompt']))

    # Step 5: Return list of tuples
    return prompts
```

## Implementation Steps

### Phase 1: Database Setup
1. Create SQLAlchemy models in `db/tables/`:
   - `agent_capabilities.py` - Agent-specific capability enablement
   - `capability_actions.py` - Action overrides table
2. Create Alembic migration for the two tables
3. Create YAML files in `services/prompt_service/capabilities/`:
   - ordering.yaml (with `always_enabled: false`)
   - reservation.yaml (with `always_enabled: false`)
   - waitlist.yaml (with `always_enabled: false`)
   - general.yaml (with `always_enabled: true`)

### Phase 2: Service Implementation
1. Update `PromptFactoryV2` in `services/prompt_service/prompts_v2.py`:
   - Replace existing `build()` method with capability-based implementation
   - Add capability management methods
2. Implement YAML loader for capability-based prompts from `capabilities/` subdirectory
3. Add repository classes for database operations (agent_capabilities, capability_actions)
4. Implement priority-based sorting and combination logic

### Phase 3: API Development
1. Create FastAPI endpoints:
   - POST/GET /api/agents/{agent_id}/capabilities - Manage agent capabilities
   - PATCH/DELETE /api/agent-capabilities/{id} - Update/remove capabilities
   - GET/POST /api/agent-capabilities/{id}/actions - Manage action overrides
   - PATCH/DELETE /api/capability-actions/{id} - Update/remove overrides
2. Add Pydantic models for request/response validation
3. Implement proper error handling and status codes
4. Add comprehensive API documentation

## Key Implementation Files

### New Files to Create:
1. `db/tables/agent_capabilities.py` - Agent-capability enablement
2. `db/tables/capability_actions.py` - Action overrides
3. `db/repositories/agent_capability_repository.py` - Repository for agent-capability operations
4. `db/repositories/capability_action_repository.py` - Repository for action override operations
5. `services/prompt_service/capabilities/ordering.yaml` - Ordering default prompts
6. `services/prompt_service/capabilities/reservation.yaml` - Reservation default prompts
7. `services/prompt_service/capabilities/waitlist.yaml` - Waitlist default prompts
8. `services/prompt_service/capabilities/general.yaml` - General info default prompts
9. `api/endpoints/capabilities.py` - FastAPI endpoints for capability management

### Files to Modify:
1. `db/tables/__init__.py` - Export new models
2. `services/prompt_service/prompts_v2.py` - Update with capability support
3. `services/prompt_service/__init__.py` - Ensure proper exports

## Validation & Constraints

### Action Naming Convention
- Enforce snake_case for all action names
- Validation regex: `^[a-z]+(_[a-z]+)*$`
- Examples: `create_order`, `cancel_reservation`, `check_status`

### Database Constraints
- Unique constraint on (agent_capability_id, action, channel) in capability_actions
- Unique constraint on (agent_id, capability_identifier) in agent_capabilities
- Capability identifiers should be lowercase, single words (e.g., 'ordering', 'reservation')
- Capability_actions entries are per-agent overrides (not defaults)

### Priority Rules
- Capability priority: 1-100 (lower number = higher priority)
- Action priority: 1-100 within each capability
- Custom priorities override defaults when specified

## Example Usage

```python
# Initialize service
prompt_factory = PromptFactoryV2()

# Work with capabilities (capabilities are defined in YAML, not database)
async with get_db_session() as session:
    # Add capability to agent by identifier
    agent_id = UUID("123e4567-e89b-12d3-a456-426614174000")
    agent_cap = await prompt_factory.add_capability_to_agent(
        session,
        agent_id=agent_id,
        capability_identifier="ordering",  # String identifier from YAML
        priority=10
    )

# Build the prompt for agent
prompts = prompt_factory.build(Channel.SMS, agent_id)

# Create an override for a specific action
async with get_db_session() as session:
    override = await prompt_factory.create_action(
        session,
        agent_capability_id=agent_cap.id,
        action="create_order",
        prompt="Custom instructions for this specific agent's order creation...",
        channel="SMS",
        priority=5
    )

    # Update capability (enable/disable and/or change priority)
    await prompt_factory.update_capability(
        session,
        agent_capability_id=agent_cap.id,
        enabled=False  # Disable the capability
    )

    # Update action override
    await prompt_factory.update_action(
        session,
        capability_action_id=override.id,
        prompt="Updated custom instructions...",  # Optional
        channel="VOICE",  # Optional
        priority=10  # Optional
    )

    # Remove override (revert to default)
    await prompt_factory.remove_action(session, override.id)
```

## Key Design Decisions
- **Replace Build Method**: Update `PromptFactoryV2` to use capability-based system
- **Flexible Capabilities**: Any capability can be added by creating a new YAML file - no hard-coded list
- **Startup Caching**: All YAML files cached at service startup for performance
- **YAML-Based Capabilities**: Capabilities defined in YAML files, not database
- **Simplified Schema**: 2 tables total - no master capability table, no history tracking (can add later)
- **YAML Defaults**: Keep default prompts and capability definitions in YAML, only store overrides in DB
- **Capability-Based**: Use "capabilities" terminology for agent abilities
- **Agent-Level**: All customizations are per-agent (no account level)
- **Priority System**: Dual-level priority (capability and action level)
- **Channel Support**: Optional channel-specific prompts
- **Always-Enabled**: Only "general" capability is always-enabled by default
- **Error Handling**: Log and skip missing capabilities for graceful degradation
