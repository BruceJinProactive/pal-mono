# Short-Term Memory

Current project context. Read this before starting any work.

Last updated: 2026-03-17

---

## Active Work

- **LiveKit migration** (started ~2025-02) — Migrating voice AI from Vapi (managed) to LiveKit (self-hosted). Major architectural shift: agent worker process replaces webhook-driven model. → `docs/plans/livekit-migration/`
- **Checkpoint auth migration** (started ~2025-02) — Migrating endpoint authorization from internal `_check_account_access` to route-level `require_checkpoint_permission` decorators. 5/8 endpoints done. → `docs/plans/auth/checkpoint-permission-migration.md`
- **Billing notifications V1** (started ~2025-02) — POC to prove Stripe webhooks can send right email to right account. Design done, partially implemented. → `docs/plans/notifications/v1-architecture.md`
- **PromptV2 capability system** (started ~2025-02) — Redesigning prompt management to be database-driven with Capabilities → Actions → Prompts hierarchy. → `docs/plans/prompt-v2/design.md`

## Recently Landed

- 2026-03-17: Fixed chat streaming session ownership so long-lived/cancelled streams close async DB sessions explicitly and do not rely on request dependency teardown
- 2025-03-01: Reorganized docs/ from `.claude/docs/` to tool-agnostic `docs/` knowledge management system

## Known Issues

- **DB connection pool leaks** (2026-03-17) — All known leak sources fixed. PR #3716 fixed 5 patterns (fire-and-forget tasks, bare sessions, generator break). PR #3725 fixed streaming session lifecycle (`chat_completions.py`, `chat.py` now own sessions via `AsyncSessionLocal()` inside generators). → `docs/records/2026-03-17-db-connection-leak-fixes.md`, `docs/records/2026-03-17-chat-stream-session-lifecycle.md`, ADR-019

## Don't Touch (fragile / in-progress)

- `agent/agent.py` LLMObs bootstrap — trace isolation depends on current structure
- `tools/registry.py` — tool registration may change with capability-based prompt system
- Auth decorators on migrated endpoints — migration in progress, check status before changing auth logic

## Upcoming

- Billing V2/V3 — multi-channel notifications with EventBridge, throttling, SMS → `docs/plans/notifications/v2-architecture.md`
