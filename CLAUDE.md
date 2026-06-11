# CLAUDE.md — Agent Harness for pal-mono

Operating rules and guardrails for AI agents. Obey hard rules unconditionally. For deep context, see `docs/README.md`.

---

## Hard Rules

### MUST

- **Use the `agentic-dev` skill** (via the Skill tool) for ALL PAL-* dev workflow tasks: planning, scoping into Notion tasks, executing task plans, shipping PRs, reviewing diffs, fixing CI, addressing CodeRabbit/reviewer feedback, resolving merge conflicts, cleaning up worktrees/branches, and updating changelogs
- **Type hints** on ALL functions — no exceptions, enforced by pyright
- **`Depends()`** for dependency injection — except DB sessions inside `StreamingResponse` generators (see ADR-019)
- **Run `./scripts/validate.sh`** before declaring any task complete (see Validation Gate below)
- **Read `docs/memory/short-term.md`** before starting any task (fragile zones, active work)
- **Check relevant accepted ADRs** before changing architecture, boundaries, or defaults — changes must obey active ADRs
- **Respect dependency flow**: API → Service → Database — `import-linter` enforces this at CI
- **Repository pattern** for all database access — never raw SQL or direct ORM queries in services
- **Async consistency** — async endpoints use `AsyncSession = Depends(db.get_db_async)`, sync use `Session = Depends(db.get_db)`
- **Update `docs/`** in the same PR as code changes (see Documentation Gate below)
- **Write tests** for new functionality and bug fixes — match existing patterns in `tests/`
- **Export new models** in `db/tables/__init__.py` before generating migrations — autogenerate only detects imported models
- **Generate DB schema revisions with the `README.md` Database Migration command** — after model/schema changes, run the documented Alembic `revision --autogenerate` command inside `pal-mono-api`, then review the generated file; do not create revision files by hand

### MUST NOT

- **Suppress type errors** — no `type: ignore`, `cast(Any, ...)`, or `# pyright: ignore`
- **Reverse dependencies** — never import from API in Service, or Service in DB layer
- **LLM calls inside tools** — tool methods must not invoke language models
- **Commit secrets** — never commit `local.env`, API keys, tokens, or credentials
- **Skip validation** — never claim work is done without running `./scripts/validate.sh`
- **Manual session management** — never use `next(db.get_db())`, always use `Depends()`
- **Mix async/sync** — never use sync DB session in async endpoint or vice versa
- **Create DB migration revision files by hand** — always use the `README.md` Database Migration command to generate Alembic revisions first, then make only necessary review fixups to the generated file
- **Delete or skip failing tests** to make a PR pass

---

## Gates (Verification Checkpoints)

### Gate 0: Pre-Work Context Load

Before starting ANY task:

1. **Read `docs/memory/short-term.md`** — check "Active Work" and "Don't Touch" sections
2. **Read `docs/memory/long-term.md`** — understand conventions and gotchas
3. **Load ADRs only as needed** — use `docs/decisions/README.md` to find relevant accepted ADRs, then read only the ones your task might affect

### Gate 1: Architecture Compliance

Before writing code:

- Verify the change does not violate any **accepted** ADRs that apply to the area you are touching
- Verify your change respects the dependency flow: **API → Service → Database**
- `utils/` must NOT import from `agent`, `api`, `db`, `services`, or `tools`
- Run `uv run lint-imports` to check — CI will block violations

```
import-linter contracts (from pyproject.toml):
  Layered:  api → services → db
  Isolated: utils → (no internal deps)
```

### Gate 2: Validation (MANDATORY before done)

```bash
./scripts/install.sh           # Install dev dependencies
./scripts/validate.sh          # Auto-fix mode (formats, sorts, lints, type-checks)
./scripts/validate.sh --check  # CI mode (check only, no modifications)
```

Runs: black → ruff → isort → pyright → lint-imports → toml-sort. Fix failures before declaring done.

### Gate 3: Documentation

If your change meets any of these criteria, update docs in the **same PR**:

| Changed | Update |
|---------|--------|
| System architecture or behavior | `docs/state/` — update relevant file, set `Last updated: YYYY-MM-DD` |
| Started new work | `docs/memory/short-term.md` — add to "Active Work" |
| Completed significant work | `docs/records/YYYY-MM-DD-description.md` + clear from short-term |
| Discovered gotcha or pattern | `docs/memory/long-term.md` — add with rationale |
| New feature or multi-step work | `docs/plans/` — create or update plan document |
| Architectural decision with tradeoffs | `docs/decisions/` — create ADR (e.g., `019-streaming-session-ownership.md`) |
| Any significant change | `docs/log.md` — append entry |

Full lifecycle rules: `docs/README.md`

### Gate 4: Security

- **Never** commit `local.env` or any file containing real credentials
- **Never** hardcode API keys, tokens, or passwords in source code
- Credentials go in `local.env` (dev) or AWS Secrets Manager (prod)
- Use `get_client_secret_with_fallback()` for credential access in code

---

## System Overview

**pal-mono** is a multi-tenant conversational AI platform for restaurant/food service businesses. Python ≥3.11, FastAPI, PostgreSQL + pgvector.

**Multi-tenant hierarchy**: Account (business) → Project (store/location) → Agent (AI persona) → User

**Entry points**:
- API: `api/main.py` → FastAPI app
- Agent: `agent/agent.py` → AI orchestration
- Database: `db/tables/` → SQLAlchemy models
- Events: `events/` → EventBridge integration

**Environments**: `dev` (local) → `lat` (latest/HEAD) → `stg` (staging) → `prd` (production)

**Architecture**: `docs/state/architecture.md` (612 lines — comprehensive reference)

---
---

## Commands

### Validation (run before claiming done)

```bash
./scripts/validate.sh          # Auto-fix mode (formats, sorts, lints, type-checks)
./scripts/validate.sh --check  # CI mode (check only, no modifications)
```

### Services

```bash
docker-compose up -d --build              # Build and run API + database
docker-compose up -d --build --force-recreate  # Force rebuild
docker-compose down                       # Stop all services
docker-compose logs -f api                # View API logs
docker restart pal-mono-api               # Restart API only
```

### Database Migrations

```bash
# IMPORTANT: Export new models in db/tables/__init__.py BEFORE generating
# IMPORTANT: Do not create revision files by hand; run the README.md command below, then review the generated file
docker exec -it pal-mono-api alembic -c db/alembic.ini revision --autogenerate -m "description"
docker exec -it pal-mono-api alembic -c db/alembic.ini upgrade head      # Apply
docker exec -it pal-mono-api alembic -c db/alembic.ini downgrade -1      # Rollback
docker exec -it pal-mono-api alembic -c db/alembic.ini history           # View history
```

Migration gotcha: empty migration generated = model not exported in `db/tables/__init__.py`.

### Testing

```bash
uv run pytest                              # Run all tests (mocked, no docker needed)
uv run pytest tests/path/to/test_file.py   # Run specific
docker exec -it pal-mono-api pytest        # Run inside container (integration tests)
```

Tests live in `tests/` directory. Test files: `test_*.py`. Async mode: auto.

---

## Configuration

1. **API Issues**: Check logs with `docker logs -f pal-mono-api`
2. **Database Issues**: Check migrations with `alembic history` and verify schema

## CI & Quality Checks

### MagicMock auto-attributes are truthy non-None objects — always pin optional fields explicitly

When a test uses `mock_request = MagicMock()` and the production code reads an
`str | None` field (e.g. `request.audio_recording_s3_uri`), the auto-created
attribute is a `MagicMock` instance — not `None`. Any code that then calls
`re.match()`, `re.search()`, or `.startswith()` on that value will raise
`TypeError: expected string or bytes-like object, got 'MagicMock'`.

**Rule:** For every `MagicMock()` request object, explicitly set all fields that
the function under test reads — including optional ones — to their intended test
values (typically `None` for unused optional fields). Do not rely on the schema
default; MagicMock does not enforce it.

```python
# Wrong — audio_recording_s3_uri will be a MagicMock, not None
mock_request = MagicMock()
mock_request.call_id = "call-123"

# Correct — pin every field the function reads
mock_request = MagicMock()
mock_request.call_id = "call-123"
mock_request.audio_recording_s3_uri = None  # must be explicit
```
