# CLAUDE.md

This file contains operating rules for AI agents working on pal-mono. For deeper context, see `docs/README.md`.

## Overview

The pal-mono service is a Python modular monolithic architecture. The system serves:

- **api** - FastAPI REST endpoints for external client interactions.
- **agent** - AI conversational system orchestrating LLM interactions and tool execution.
- **db** - SQLAlchemy models, migrations, and repository pattern for data access.
- **events** - AWS EventBridge integration for asynchronous event-driven communication.
- **services** - Business logic layer enforcing rules between API and database.
- **tools** - External tool-calling system integrations (Adora, Toast, Square, Yelp, etc.) for AI agents.

For detailed architecture: `docs/state/architecture.md`
For conventions and patterns: `docs/memory/long-term.md`
For current active work: `docs/memory/short-term.md`
For all documentation: `docs/README.md`

## Important Notes

- Enforce a strict dependency flow: API → Service → Database, with no shared packages.
- All functions must have type hints
- Use FastAPI's `Depends()` for dependencies

## Commands

### Running Services

```bash
# Build and run both API and database locally
docker-compose up -d --build

# Force rebuild from scratch
docker-compose up -d --build --force-recreate

# Stop services
docker-compose down

# View logs
docker-compose logs -f api
```

### Local Environment Setup

```bash
# Install dependencies using uv (creates virtual environment automatically)
./scripts/install.sh

# Or directly with uv:
uv sync --all-extras
```

### Dependency Management

```bash
# Update lock file after adding new dependencies to pyproject.toml
./scripts/upgrade.sh
# or: uv lock

# Upgrade all dependencies to latest compatible versions
./scripts/upgrade.sh all
# or: uv lock --upgrade
```

### Validation

```bash
# Run all validation checks (format, lint, type check, import-linter, toml-sort)
./scripts/validate.sh

# Run validation in check mode (CI-style, no auto-fix)
./scripts/validate.sh --check

# Format with black
uv run black .

# Sort imports
uv run isort .

# Lint with ruff
uv run ruff check . --fix

# Type check with pyright
uv run pyright .

# Check import architecture
uv run lint-imports

# Sort pyproject.toml
uv run toml-sort pyproject.toml --in-place
```

### Testing

```bash
# Start the containers first
docker-compose up -d --build

# Run tests with pytest
docker exec -it pal-mono-api pytest
```

## Project Structure

```tree
pal-mono/
├── agent/              # AI agent system (core conversational logic)
├── api/                # FastAPI REST API
├── services/           # Business logic layer
├── db/                 # Database layer
├── events/             # AWS EventBridge integration for async events
├── tools/              # AI agent tools
├── utils/              # Shared utilities
├── scripts/            # Development and deployment scripts
└── .github/workflows/  # CI/CD pipelines
```

## Key Concepts

### Multi-Tenant Architecture

- **Accounts**: Business accounts (restaurants)
- **Projects**: Stores, belongs to a business account
- **Agents**: AI agent configurations with persona and settings
- **Users**: User accounts associated with accounts

## Tools

For full tool development guidelines, see `docs/memory/long-term.md` → "Tool Development" section.

Quick reference:
- Inherit from `Toolkit`, use `@tool` decorator (from ddtrace, not Agno), register in `tools/registry.py`
- Docstrings max 1024 chars with when-to-use / when-not-to-use
- Never make LLM calls inside tool methods
- Validate inputs with Pydantic models

## Development Workflow

### Making Changes

1. **Code Changes**: Edit files in your preferred editor
2. **Validate All**: Run `./scripts/validate.sh`

### Configuration

The system uses environment-based configuration:

- **RUNTIME_ENV**: `dev` (local), `lat`, `stg`, `prd`
- **Local secrets**: Use `local.env` file (see docker-compose.yml)
- **Production secrets**: AWS Secrets Manager

## Common Tasks

### Viewing Logs

```bash
# API logs
docker logs -f pal-mono-api

# Database logs
docker logs -f pal-mono-db
```

### Restarting Services

```bash
# Restart all services
docker-compose restart

# Restart API only
docker restart pal-mono-api
```

### Database Migrations

```bash
# Generate a new migration after modifying tables
docker exec -it pal-mono-api alembic -c db/alembic.ini revision --autogenerate -m "description"

# Apply migrations
docker exec -it pal-mono-api alembic -c db/alembic.ini upgrade head

# Rollback one migration
docker exec -it pal-mono-api alembic -c db/alembic.ini downgrade -1

# View migration history
docker exec -it pal-mono-api alembic -c db/alembic.ini history
```

### Database Access

```bash
# Connect to local database
psql -h localhost -U app -d app
# Password: app

# Or via Docker
docker exec -it pal-mono-db psql -U app -d app
```

### Debugging

1. **API Issues**: Check logs with `docker logs -f pal-mono-api`
2. **Database Issues**: Check migrations with `alembic history` and verify schema
