# PromptV2 Capability-Based Prompt System

> **Date:** 2026-01-21

## Summary

Replaced the monolithic prompt builder with a database-driven, capability-based system. Agents now have modular capabilities (ordering, reservation, waitlist, etc.) with YAML defaults and per-agent DB overrides.

## What Changed

### Database (2 new tables)

- **`agent_capabilities`**: Links agents to capabilities with priority and enabled/disabled state. Unique on `(agent_id, capability_identifier)`.
- **`capability_actions`**: Per-agent action overrides with prompt text, channel filter, and priority. Only stores overrides — defaults live in YAML.

### Capability YAML Files

7+ capability definitions under `services/prompt_service/capabilities/`:
- `general.yaml` (always_enabled)
- `ordering.yaml`
- `reservation.yaml`
- `waitlist.yaml`
- `call_transfer.yaml`
- `api_reference.yaml`
- `communication_style.yaml`

### PromptFactoryV2

`services/prompt_service/prompts_v2.py` — `build(channel, agent_id)` method:
1. Loads all YAML capability definitions (cached at startup)
2. Checks which capabilities are enabled for the agent (always_enabled or via `agent_capabilities`)
3. Merges YAML defaults with DB overrides (DB takes precedence)
4. Filters by channel, sorts by priority
5. Returns `list[tuple[str, str]]` of (title, prompt)

### Migrations

- `2026-01-03`: Initial `agent_capabilities` and `capability_actions` tables
- `2026-01-21`: Added `enabled` column to `capability_actions`

## Key Design Decisions

- **YAML defaults, DB overrides**: Avoids bloating the DB with defaults; easy to ship new capabilities via code
- **No master capability table**: Capabilities are defined by YAML files, not a DB table
- **Per-agent only**: No account-level customization (can be added later)
- **Channel support**: Actions can be channel-specific (SMS, VOICE, EMAIL) or ALL

## Origin

Plan: `docs/plans/prompt-v2/design.md` (now archived)
