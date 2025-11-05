# CLAUDE.md

This file contains information for Claude to help with the pal-mono repository.

## Overview

The pal-mono service is a Python monolith that provides a multi-tenant conversational AI platform designed for restaurant and food service businesses. The system serves:
- **api** - A FastAPI-based REST API that powers AI agents with voice, SMS, and web chat capabilities
- **app** - A Streamlit web app that demos the service functionalities

### Key Capabilities
- Multi-channel AI agents (voice via VAPI, SMS via Twilio, web chat)
- POS integrations (Toast, Square, Adora, OLO, MenuSifu)
- Reservation system integrations (OpenTable, Resy, Yelp)
- Personalized memory (mem0ai) and knowledge base (RAG with LlamaIndex + Pinecone)
- Multi-tenant SaaS with Stripe billing
- Quality assurance with checkpoints and checklists

For detailed architecture information, see `.claude/docs/architecture.md`.

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
# Run all validation checks
./scripts/validate.sh

# Format with black
black .

# Sort imports
isort .

# Lint with ruff
ruff check . --fix

# Type check with pyright
pyright .
```

### Testing

```bash
# Start the containers first
docker-compose up -d --build

# Run tests
./scripts/test.sh
```

### API and App Access

- API documentation: http://localhost:8000/docs#/
- Web app: http://localhost:8501/

## Project Structure

```
pal-mono/
├── agent/              # AI agent system (core conversational logic)
│   ├── framework/      # AgnoAgent wrapper with streaming support
│   ├── model/          # Multi-provider LLM abstraction (OpenAI, Anthropic, etc.)
│   ├── memory/         # Personalized memory with mem0ai
│   ├── knowledge/      # RAG system with LlamaIndex + Pinecone
│   ├── tool/           # Tool management and registry
│   ├── storage/        # Conversation history retrieval
│   └── guardrails/     # Content safety (AWS Bedrock)
│
├── api/                # FastAPI REST API
│   ├── routes/         # API endpoints by domain (chat, admin, integrations)
│   └── schemas/        # Pydantic request/response models
│
├── services/           # Business logic layer (29 services)
│   ├── account_service/
│   ├── agent_service/
│   ├── message_service/  # Core message processing
│   ├── integration_service/
│   └── ...
│
├── db/                 # Database layer
│   ├── tables/         # SQLAlchemy table definitions (29 tables)
│   ├── repositories/   # Repository pattern for data access (25 repos)
│   └── migrations/     # Alembic database migrations
│
├── tools/              # AI agent tools (21 tools)
│   ├── *_tool/         # POS, reservation, communication integrations
│   ├── base/           # Base tool abstractions
│   ├── registry.py     # Central tool registry
│   └── TOOL_STANDARDS.md
│
├── utils/              # Shared utilities
├── scripts/            # Development and deployment scripts
├── workspace/          # Agno workspace configuration
└── .github/workflows/  # CI/CD pipelines
```

## Key Concepts

### Agent System
The agent system (`/agent`) orchestrates AI conversations by:
1. Loading agent configuration (persona, model, tools, memory, knowledge)
2. Retrieving conversation history from storage
3. Fetching relevant memories (mem0ai) and knowledge (RAG)
4. Streaming responses from LLM with tool calling support
5. Updating memory in background

### Service Layer
Services (`/services`) implement business logic and act as the bridge between API endpoints and the database. Each service:
- Handles a specific domain (accounts, agents, messages, integrations, etc.)
- Uses repositories for data access
- Contains business validation and orchestration logic

### Tools
Tools (`/tools`) extend agent capabilities with external integrations:
- POS systems: Toast, Square, Adora, OLO, MenuSifu
- Reservations: OpenTable, Resy, Yelp, MiniTable
- Communication: SMS, Voice (VAPI)
- Other: Catering, escalation

Each tool follows standards defined in `tools/TOOL_STANDARDS.md`.

### Multi-Tenant Architecture
- **Accounts**: Business accounts (restaurants)
- **Agents**: AI agent configurations with persona and settings
- **Projects**: Link accounts to agents
- **Users**: User accounts associated with projects

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

## Development Workflow

### Making Changes

1. **Code Changes**: Edit files in your preferred editor
2. **Format Code**: Run `black .` and `isort .`
3. **Lint**: Run `ruff check . --fix`
4. **Type Check**: Run `pyright .`
5. **Test**: Run `./scripts/test.sh` (requires `ag ws up` to be running)
6. **Validate All**: Run `./scripts/validate.sh`

### Adding New Features

#### Adding a New API Endpoint
1. Create Pydantic schemas in `/api/schemas/`
2. Add route handler in `/api/routes/`
3. Implement business logic in appropriate service in `/services/`
4. Add database operations in repository if needed

#### Adding a New Tool
1. Create tool directory in `/tools/` following `TOOL_STANDARDS.md`
2. Implement tool class inheriting from base tool
3. Register tool in `/tools/registry.py`
4. Update agent configuration to include new tool

#### Adding a New Service
1. Create service directory in `/services/`
2. Implement service class with business logic
3. Add repository for data access if needed
4. Import and use in API routes

### Configuration

The system uses environment-based configuration:
- **RUNTIME_ENV**: `dev` (local), `lat`, `stg`, `prd`
- **Local secrets**: `workspace/secrets/dev_app_secrets.yml`
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
ag ws restart

# Restart API only
docker restart pal-mono-api
```

### Debugging

1. **API Issues**: Check logs with `docker logs -f pal-mono-api`
2. **Database Issues**: Check migrations with `alembic history` and verify schema
3. **Integration Issues**: Check integration credentials in database
4. **Agent Issues**: Review agent configuration and tool logs

## Testing

```bash
# Run all tests with coverage
./scripts/test.sh

# Run specific test file (inside container)
docker exec -it pal-mono-api pytest services/agent_service/test_agent_service.py

# Run with verbose output
docker exec -it pal-mono-api pytest -v
```

## Important Notes

### Code Quality Standards
- **Type Hints**: All functions must have type hints
- **Async/Await**: Use async functions throughout (FastAPI, SQLAlchemy)
- **Logging**: Use structured JSON logging (see `utils/CLAUDE.md`)
- **Error Handling**: Proper exception handling with meaningful messages

### Architecture Patterns
- **Repository Pattern**: All database access through repositories
- **Service Layer**: Business logic in services, not in routes
- **Dependency Injection**: Use FastAPI's `Depends()` for dependencies
- **Async-First**: Everything is async for performance

### Security Considerations
- Never commit credentials or API keys
- Use AWS Secrets Manager for production secrets
- Validate all inputs with Pydantic
- Use CORS configuration appropriate for environment

## Resources

- **Architecture Details**: `.claude/docs/architecture.md`
- **Tool Standards**: `tools/TOOL_STANDARDS.md`
- **Logging Guidelines**: `utils/CLAUDE.md`
- **API Documentation**: http://localhost:8000/docs when running locally