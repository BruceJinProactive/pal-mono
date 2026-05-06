# Long-Term Memory

Institutional knowledge for the pal-mono codebase. Every entry has a rationale — no rules without "because."

Last curated: 2026-04-27

---

## Conventions

### Code Style

- All functions must have **type hints** — enforced project-wide, no exceptions
- Use FastAPI's `Depends()` for dependency injection, except DB sessions owned inside long-lived `StreamingResponse` generators/tasks (see ADR-019)
- Enforce strict dependency flow: **API → Service → Database** — `lint-imports` enforces this at CI
- Format with `black`, sort imports with `isort`, lint with `ruff`, type check with `pyright`
- Run `./scripts/validate.sh` before every PR — it runs all checks in sequence

### Context Management in Tools

- Keep tool return messages concise yet complete — no unnecessarily large data structures
- For large datasets (menus, catalogs), use query engines instead of returning full data
- Example: Return "Menu contains 50 items. Use search_menu(query) for specifics" instead of full catalog

### Authentication

- **Standard**: Fetch credentials from AWS Secrets Manager via `get_client_secret_with_fallback()`
- **Alternative** (dev/testing only): Accept tokens from `raw_config` as constructor parameters (e.g., Square's `access_token` fallback)
- Default to AWS Secrets Manager; use `raw_config` token fallbacks only when a tool explicitly supports a dev/testing-only override

### Database

- Use repository pattern for all data access (56 repository classes)
- Alembic for migrations — generate revision files after model changes or DB schema will diverge from code
- Multi-tenant architecture: Account → Project → Agent hierarchy
- PostgreSQL + pgvector for vector storage

### Configuration

- Environment-based: `RUNTIME_ENV` = `dev` (local), `lat`, `stg`, `prd`
- Local secrets: `local.env` file (gitignored)
- Production secrets: AWS Secrets Manager

---

## Architecture Patterns

### Dependency Flow (ENFORCED)

```text
API → Service → Database
```

- API layer handles HTTP, validation, routing
- Service layer contains business logic, orchestration
- Database layer handles persistence via repository pattern
- **No reverse dependencies** — `lint-imports` will catch violations

### Event-Driven Communication

- AWS EventBridge for async cross-service communication
- Events follow `BaseEvent` pattern in `/events/schema.py`
- Event naming: `{domain}.{entity}.{action}` (e.g., `business.token.refresh_requested`)
- Published to `pal-main-event-bus`

### Multi-Tenant Isolation

- **Accounts** = business accounts (restaurants)
- **Projects** = stores/locations, belong to an account
- **Agents** = AI agent configurations with persona and settings
- Project-level isolation for most operations

---

## Architecture Anti-Patterns

- **Never** suppress type errors with `type: ignore`, `cast(Any, ...)`, or `# pyright: ignore`
- **Never** import from API layer in Service layer (or any reverse dependency)
- **Never** return full catalogs from tools — use query engines for large datasets
- **Never** make additional LLM calls inside tool methods
- **Never** skip `@observe(as_type="tool")` decorator on registered tool methods (Langfuse tracing breaks)
- **Never** use `Optional[]` parameters without defaults and clear documentation

---

## Integration Gotchas

- **Stripe webhooks** can fire multiple times for the same event — always check idempotency
- **Square OAuth tokens** expire every 30 days — `SQUARE_TOKEN_REFRESHER` handles automatic refresh
- **Toast API** menu data can be very large — use the indexer pipeline (Toast → Pinecone) rather than returning raw data
- **`pal_agents.AdoraSpec` rejects `lookup_menu_data`** — treat ProjectIntegration-backed specs as the source of truth for Adora configuration and ignore stale raw_config-only lookup payloads, because Pydantic now forbids that extra field
- **Vapi** is fully removed from code — `tools/vapi_tool/`, `api/routes/integrations/vapi/`, and the `assistant-request` webhook are gone; `VoiceProvider` enum is LiveKit-only and explicitly rejects `"vapi"`. Residual legacy only: the `conversations.vapi_control_url` column (historical data; still threaded through DTOs/repos/admin schema/`message_service` for back-compat) and a few stale docstrings/log strings. Do not build new voice functionality against a Vapi code path — none exists.
- **`api` is not a `customer_phone` channel** (2026-04-25, PR #4086): API-channel requests no longer have `customer_phone` auto-populated from email-derived values. Eval flows that simulate phone customers over API must inject `customer_phone` through the `context_modifier` pattern (see active work), not through `Message.Metadata`.
- **ADR-007 migration state**: Agno and `pal-agents` coexist during the migration. Prefer `pal-agents` (`PalAgent` with `Spec` and `RuntimeContext`) for new LiveKit-oriented agent work; maintain Agno only where existing integrations still depend on it. Current pinned version: `pal-agents` v0.2.265.
- **Trace context inheritance (general)**: Monitoring LLM calls can inherit voice-agent trace context, causing spans to appear in wrong trace trees. Use explicit trace isolation when running LLM analysis outside the agent pipeline. Applies to both Langfuse (`@observe`) and OTel spans.
- **`asyncio.create_task` leaks OTel trace context into fire-and-forget work** (2026-05-05, PAL-10344): the service boots via `opentelemetry-instrument` (`opentelemetry-distro` in `pyproject.toml`) so every FastAPI handler runs inside an auto-created root span — there is no explicit `FastAPIInstrumentor().instrument_app(...)` call, so this is easy to miss. `asyncio.create_task` snapshots the current `contextvars` including that OTel span context, and because `trace_id` is not cleared when a span ends, long-lived background tasks (and everything they spawn via `asyncio.gather`) silently share a `trace_id` with the originating HTTP request. Symptom: all Langfuse observations in an eval run shared one trace. Fix pattern: at the logical trace boundary call `opentelemetry.context.attach(opentelemetry.context.Context())` to detach the leaked parent, then open your own root span. See `services/eval_service/_tracing.py::scenario_trace_boundary` for the reference implementation and `docs/records/2026-05-05-eval-langfuse-trace-boundary.md` for the full diagnosis. Audit other fire-and-forget tasks spawned from HTTP handlers before extending tracing to them.
- **Observability split (post-ADR-013 supersede, 2026-04-25)**: LLM tracing is **Langfuse** (`@observe`, `langfuse.get_client()`), general app tracing is **OpenTelemetry** (Grafana Tempo), and metrics go through OTel (`utils/otel.py`) after the StatsD migration. Do not re-import `ddtrace.llmobs` or `utils/dd.py` — both pathways were removed.

---

## Lessons Learned

- **Long-lived async responses must own their DB session** (2026-03-17): Releasing the current transaction before LLM work is not enough for `StreamingResponse` or other cancellation-prone flows. If a request-scoped `AsyncSession` survives inside a long-lived generator or task, SQLAlchemy may later warn that a non-checked-in asyncpg connection is being garbage-collected. Fix the ownership boundary instead: create and close `AsyncSessionLocal()` inside the generator/task that owns the lifetime.
- **Monitoring trace isolation** (2025-02-14): Monitoring LLM calls (image/video analysis) were inheriting active voice-agent trace context. Fix: explicit trace isolation in `/services/monitoring_service/_llm.py`. See `docs/records/2025-02-14-monitoring-trace-fix.md`. Still applies under Langfuse—wrap the isolated call so it doesn't adopt the parent `@observe` span.
- **Permission decorators** have limitations: endpoints with resource IDs in form data, query params, or request body can't use simple route-level decorators. Need custom permission handlers that traverse the resource hierarchy. See `docs/state/auth.md`.
- **Event-driven vs completion events**: For observability, the Langfuse SDK + OTel exporter is simpler and more effective than completion events + CloudWatch. Fewer moving parts, better developer experience.
- **Don't use `Message.Metadata` as a back-door for eval-only context** (2026-04-25): When eval flows needed `customer_phone` after it stopped auto-populating for the API channel, the clean fix is an optional `context_modifier` callback on the service entry point that only the eval driver supplies—not a new optional field on the public request schema. Keeps the API surface honest and keeps eval-only concerns in the eval layer.
- **Frozen dataclasses for cross-layer payloads** (2026-04): The PAL-10000’s series moved analytics/change-log/monitoring/order/etc. payloads from mutable dicts to frozen dataclasses. Prefer frozen dataclasses (not TypedDicts or free-form dicts) for any new DTO that crosses layer boundaries — immutability + explicit fields catch drift at type-check time.
