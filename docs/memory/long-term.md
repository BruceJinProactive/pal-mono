# Long-Term Memory

Institutional knowledge for the pal-mono codebase. Every entry has a rationale — no rules without "because."

Last curated: 2026-03-17

---

## Conventions

### Code Style

- All functions must have **type hints** — enforced project-wide, no exceptions
- Use FastAPI's `Depends()` for all dependency injection
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
- Always ask which auth method to use when creating new tools or changing existing ones

### Database

- Use repository pattern for all data access (25 repository classes)
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

- **Never** suppress type errors with `as any`, `@ts-ignore`, `@ts-expect-error`
- **Never** import from API layer in Service layer (or any reverse dependency)
- **Never** return full catalogs from tools — use query engines for large datasets
- **Never** make additional LLM calls inside tool methods
- **Never** skip `@tool` decorator on registered tool methods (Datadog tracing breaks)
- **Never** use `Optional[]` parameters without defaults and clear documentation

---

## Integration Gotchas

- **Stripe webhooks** can fire multiple times for the same event — always check idempotency
- **Square OAuth tokens** expire every 30 days — `SQUARE_TOKEN_REFRESHER` handles automatic refresh
- **Toast API** menu data can be very large — use the indexer pipeline (Toast → Pinecone) rather than returning raw data
- **Vapi** `assistant-request` webhook has a tight timeout — cache agent configs where possible
- **ddtrace context inheritance**: Monitoring LLM calls can inherit voice agent trace context, causing spans to appear in wrong trace trees. Use trace isolation when running LLM analysis outside the agent pipeline.
- **Agno is being dropped** in favor of `pal-agents` (`PalAgent` with `Spec` and `RuntimeContext`)

---

## Lessons Learned

- **Long-lived async responses must own their DB session** (2026-03-17): Releasing the current transaction before LLM work is not enough for `StreamingResponse` or other cancellation-prone flows. If a request-scoped `AsyncSession` survives inside a long-lived generator or task, SQLAlchemy may later warn that a non-checked-in asyncpg connection is being garbage-collected. Fix the ownership boundary instead: create and close `AsyncSessionLocal()` inside the generator/task that owns the lifetime.
- **Monitoring trace isolation** (2025-02-14): Monitoring LLM calls (image/video analysis) were inheriting active voice-agent trace context in Datadog. Fix: explicit trace isolation in `/services/monitoring_service/_llm.py`. See `docs/records/2025-02-14-monitoring-trace-fix.md`.
- **Permission decorators** have limitations: endpoints with resource IDs in form data, query params, or request body can't use simple route-level decorators. Need custom permission handlers that traverse the resource hierarchy. See `docs/state/auth.md`.
- **Event-driven vs completion events**: For observability, Datadog Lambda Extension is simpler and more effective than completion events + CloudWatch. Fewer moving parts, better developer experience.
