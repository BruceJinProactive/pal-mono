# CLAUDE.md

This file contains information for Claude to help with the pal-mono repository.

## Overview

The pal-mono service is a Python modular monolithic architecture. The system serves:

- **api** - FastAPI REST endpoints for external client interactions.
- **agent** - AI conversational system orchestrating LLM interactions and tool execution.
- **db** - SQLAlchemy models, migrations, and repository pattern for data access.
- **events** - AWS EventBridge integration for asynchronous event-driven communication.
- **services** - Business logic layer enforcing rules between API and database.
- **tools** - External tool-calling system integrations (Adora, Toast, Square, Yelp, etc.) for AI agents.

For detailed architecture information, see `.claude/docs/architecture.md`.

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

### Core Requirements

- Inherit from `Toolkit`, initialize with `super().__init__(name="tool_name")`; without inheriting from Toolkit, the agent system wouldn't be able to discover or invoke the tool methods properly.
- `@tool` decorator required for all registered methods; the @tool decorator is from ddtrace.llmobs.decorators, it is for Debugging/Tracing/Observability on Datadog
- `@params_validate()` required only for methods with parameters
- Register all tools in `tools/registry.py`
- For complex tools only, decompose into smaller, focused, single-purpose helper functions; avoid unnecessary decomposition for simple tools or over-engineering

### Docstrings (max 1024 chars)

Must include:

1. Concise description (1 line)
2. When to use (triggering conditions)
3. Do NOT use when (tool boundaries)
4. Args (formats, constraints, examples)
5. Returns (success/error formats)

### Parameters

- **Optional params:** Use defaults and `Optional[]` type hints, document clearly
- **No LLM calls:** Don't make additional LLM calls inside tool methods

### Validation

- Validate ALL inputs before API calls using Pydantic models
- Use `Field()` with clear descriptions for LLM guidance

### Authentication (always ask which method to use upon new tool creation or changes)

**Standard:** Fetch credentials from AWS Secrets Manager via `get_client_secret_with_fallback()`

**Alternative (for development and testing purposes):** Accept tokens from `raw_config` as constructor parameters (e.g., Square's `access_token` fallback)

### Tool Scale Guidelines

- Guidance Principle: Register 1-3 tools per agent for optimal performance; up to 10 tools acceptable if necessary; avoid exceeding 15 tools as accuracy degrades
- Note: Tool scope depends on the API documentation and client requirements; always consider and ask for context before implementation.

### Context Management

- Keep tool return messages concise yet complete; include all essential information without omitting important details; avoid unnecessarily large data structures.
- For large datasets (menus, catalogs), use query engines instead of returning full data
- Example: Return "Menu contains 50 items. Use search_menu(query) for specifics" instead of full catalog

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
