# Short-Term Memory

Current project context. Read this before starting any work.

Last updated: 2025-03-01

---

## Active Work

- **LiveKit migration** (started ~2025-02) — Migrating voice AI from Vapi (managed) to LiveKit (self-hosted). Major architectural shift: agent worker process replaces webhook-driven model. → `docs/plans/livekit-migration/`
- **Checkpoint auth migration** (started ~2025-02) — Migrating endpoint authorization from internal `_check_account_access` to route-level `require_checkpoint_permission` decorators. 5/8 endpoints done. → `docs/plans/auth/checkpoint-permission-migration.md`
- **Billing notifications V1** (started ~2025-02) — POC to prove Stripe webhooks can send right email to right account. Design done, partially implemented. → `docs/plans/notifications/v1-architecture.md`
- **PromptV2 capability system** (started ~2025-02) — Redesigning prompt management to be database-driven with Capabilities → Actions → Prompts hierarchy. → `docs/plans/prompt-v2/design.md`

## Recently Landed

- 2025-03-01: Reorganized docs/ from `.claude/docs/` to tool-agnostic `docs/` knowledge management system

## Known Issues

- (none currently documented)

## Don't Touch (fragile / in-progress)

- `agent/agent.py` LLMObs bootstrap — trace isolation depends on current structure
- `tools/registry.py` — tool registration may change with capability-based prompt system
- Auth decorators on migrated endpoints — migration in progress, check status before changing auth logic

## Upcoming

- Billing V2/V3 — multi-channel notifications with EventBridge, throttling, SMS → `docs/plans/notifications/v2-architecture.md`
