# Architecture Overview

## Quick Reference

**System Type**: Multi-tenant conversational AI platform for restaurant/food service
**Primary Language**: Python 3.11
**Web Framework**: FastAPI (async)
**Database**: PostgreSQL + pgvector
**AI Framework**: Agno (v1.7.6)
**Architecture Style**: Monolithic with event-driven components
**Deployment**: Docker (local), AWS (production)

**Key Metrics**:
- 29 database tables
- 25 repository classes
- 29 business services
- 21 AI agent tools
- 8+ API route groups
- 4 environments (dev/lat/stg/prd)

**Entry Points**:
- API: `/api/main.py` → FastAPI app
- Agent: `/agent/agent.py` → AI orchestration
- Database: `/db/tables/` → SQLAlchemy models

## System Overview

pal-mono is a multi-tenant conversational AI platform designed for restaurant and food service businesses. It provides AI-powered agents that can handle customer interactions across multiple channels (voice, SMS, web chat) while integrating with POS systems, reservation platforms, and other business tools.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Client Layer                             │
│  (Web Chat, SMS via Twilio, Voice via VAPI, API Clients)       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI Application                         │
│  - REST API Endpoints (/v1/chat, /v1/admin, /v1/integrations)  │
│  - Request Validation (Pydantic)                                 │
│  - CORS & Middleware                                             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Service Layer                              │
│  - 29 Business Services (account, agent, message, integration)  │
│  - Business Logic & Orchestration                                │
│  - Transaction Management                                        │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
    │ Agent System │  │   Database   │  │ External APIs│
    │              │  │   (Postgres) │  │ & Services   │
    └──────────────┘  └──────────────┘  └──────────────┘
```

## Component Interaction Matrix

| Component | Talks To | Used By | Purpose |
|-----------|----------|---------|---------|
| **API Routes** | Services | External clients | HTTP endpoints |
| **Services** | Repositories, Agent, External APIs | API routes, other services | Business logic |
| **Repositories** | Database (SQLAlchemy) | Services | Data access |
| **Agent** | LLM providers, Tools, Memory, Knowledge | message_service | AI orchestration |
| **Tools** | External APIs (POS, Reservations) | Agent | External integrations |
| **Memory** | mem0ai API | Agent | User personalization |
| **Knowledge** | Pinecone, LlamaIndex | Agent | RAG/document retrieval |
| **Database** | PostgreSQL | Repositories | Data persistence |

**Key Data Flow**:
1. Client → API Routes → Services → Repositories → Database
2. Client → API Routes → message_service → Agent → LLM/Tools/Memory/Knowledge
3. Agent → Tools → External APIs (POS, reservations, etc.)

## Core Components

### 1. API Layer (`/api`)

**Technology**: FastAPI with async/await support

**Structure**:
- `/api/main.py` - Application factory with lifespan management
- `/api/routes/` - REST endpoint definitions organized by domain
- `/api/schemas/` - Pydantic models for request/response validation

**Key Routes**:
- `/v1/chat` - Main conversational interface (streaming and non-streaming)
- `/v1/admin` - Account, agent, project, and user management
- `/v1/integrations` - Third-party POS and reservation system integrations
- `/v1/assets` - Asset management (S3-backed)
- `/v1/operation` - Checklists and checkpoints for quality assurance
- `/v1/catering` - Catering request handling

**Features**:
- Environment-based CORS configuration
- Automatic OpenAPI documentation at `/docs`
- Request validation with Pydantic
- Async request handling throughout

### 2. Agent System (`/agent`)

The core AI agent implementation providing conversational capabilities.

**Architecture**:

```
┌─────────────────────────────────────────────────────────────┐
│                      Agent (agent.py)                        │
│  - Orchestrates conversation flow                            │
│  - Manages streaming and non-streaming responses             │
│  - Coordinates all submodules                                │
└─────────────────────────────────────────────────────────────┘
           │
           ├──► Framework (framework/agno.py)
           │    - Agent wrapper with streaming support
           │    - Streaming with filler words
           │    - Datadog LLM observability
           │
           ├──► Model (model/)
           │    - Multi-provider support (OpenAI, Anthropic, Google, Groq)
           │    - Model abstraction layer
           │
           ├──► Memory (memory/)
           │    - mem0ai integration for personalized memory
           │    - 5-minute TTL cache
           │    - Background async updates
           │
           ├──► Knowledge (knowledge/)
           │    - LlamaIndex + Pinecone for RAG
           │    - Cohere embeddings
           │    - Multi-modal document retrieval
           │
           ├──► Tool (tool/)
           │    - Dynamic tool loading
           │    - 21 specialized tools
           │
           ├──► Storage (storage/)
           │    - Conversation history retrieval
           │
           └──► Guardrails (guardrails/)
                - AWS Bedrock content safety
```

**Configuration** (`/agent/config.py`):
- Persona settings (name, role, description, instructions)
- Model selection and parameters
- Memory, knowledge, and tool configuration
- Voice settings (VAPI integration)
- Transcription configuration

### 3. Service Layer (`/services`)

29 specialized services implementing business logic:

| Service | Category | Purpose | Key Dependencies |
|---------|----------|---------|------------------|
| `account_service` | Core | Multi-tenant account management | accounts table |
| `agent_service` | Core | Agent configuration and lifecycle | agents table |
| `project_service` | Core | Project management (account + agent) | projects table |
| `user_service` | Core | User authentication and management | users table |
| `message_service` | Communication | Message processing (streaming/non-streaming/relay) | messages, agent_service |
| `voice_service` | Communication | Voice call handling | phonecalls, VAPI |
| `email_service` | Communication | Email notifications | Email provider |
| `relay_service` | Communication | External message relay | Message broker |
| `integration_service` | Integration | Third-party integration management | integration table |
| `knowledge_service` | Integration | Integration-specific knowledge bases | Pinecone, LlamaIndex |
| `adora_service` | Integration | Adora POS integration | Adora API |
| `olo_service` | Integration | OLO ordering integration | OLO API |
| `square_service` | Integration | Square POS integration | Square API |
| `toast_service` | Integration | Toast POS integration | Toast API |
| `opentable_service` | Integration | OpenTable reservations | OpenTable API |
| `resy_service` | Integration | Resy reservations | Resy API |
| `yelp_service` | Integration | Yelp reservations | Yelp API |
| `subscription_service` | Business | Stripe billing management | Stripe, subscriptions table |
| `catering_service` | Business | Catering workflow | EventBridge, catering_requests |
| `analytics_service` | Business | Usage analytics | Slack, analytics data |
| `feedback_service` | Business | User feedback collection | feedback table |
| `campaign_service` | Business | Marketing campaigns | campaigns table |
| `faq_service` | Business | FAQ management | faqs table |
| `prompt_service` | Business | Prompt templates | prompts table |
| `asset_service` | Business | Asset storage | S3 |
| `checklist_service` | Operations | Operational checklists | checklists table |
| `checkpoint_service` | Operations | Quality review checkpoints | checkpoints table |
| `transaction_service` | Operations | Transaction tracking | orders, reservations |
| `vision_service` | Operations | Image processing | Computer vision API |

### 4. Database Layer (`/db`)

**Technology**: PostgreSQL with pgvector extension

**Components**:
- `/db/tables/` - SQLAlchemy 2.0 table definitions (29 tables)
- `/db/repositories/` - Repository pattern for data access (25 repositories)
- `/db/migrations/` - Alembic migrations

**Key Tables**:
- `accounts` - Business accounts with subscription and industry
- `agents` - AI agent configurations
- `projects` - Account + agent associations
- `conversations` & `messages` - Chat history
- `phonecalls` - Voice call records
- `orders` & `reservations` - Transaction records
- `integration` - Third-party integration credentials
- `checklists` & `checkpoints` - Quality assurance

**Connection Management**:
- Async connection pooling (30 connections, 50 max overflow)
- Both sync and async session support
- Transaction management with proper rollback

### 5. Tools System (`/tools`)

21 specialized tools that extend agent capabilities:

| Tool | Category | Purpose | File Path |
|------|----------|---------|-----------|
| `toast_tool` | POS | Toast POS operations | `/tools/toast_tool/` |
| `square_tool` | POS | Square POS operations | `/tools/square_tool/` |
| `adora_tool` | POS | Adora POS operations | `/tools/adora_tool/` |
| `olo_tool` | POS | OLO ordering | `/tools/olo_tool/` |
| `menusifu_tool` | POS | MenuSifu POS operations | `/tools/menusifu_tool/` |
| `opentable_tool` | Reservation | OpenTable bookings | `/tools/opentable_tool/` |
| `resy_tool` | Reservation | Resy bookings | `/tools/resy_tool/` |
| `resy_with_reservation_tool` | Reservation | Resy with existing reservation | `/tools/resy_with_reservation_tool/` |
| `resy_without_reservation_tool` | Reservation | Resy without reservation | `/tools/resy_without_reservation_tool/` |
| `yelp_tool` | Reservation | Yelp bookings | `/tools/yelp_tool/` |
| `yelp_credit_card_tool` | Reservation | Yelp with credit card | `/tools/yelp_credit_card_tool/` |
| `yelp_no_credit_card_tool` | Reservation | Yelp without credit card | `/tools/yelp_no_credit_card_tool/` |
| `minitable_tool` | Reservation | MiniTable bookings | `/tools/minitable_tool/` |
| `sms_tool` | Communication | Send SMS via Twilio | `/tools/sms_tool/` |
| `vapi_tool` | Communication | Voice API integration | `/tools/vapi_tool/` |
| `catering_tool` | Business | Catering requests | `/tools/catering_tool/` |
| `escalation_tool` | Operations | Escalate to human | `/tools/escalation_tools/` |

**Tool Standards** (`/tools/TOOL_STANDARDS.md`):
- Consistent structure: `__init__.py`, `tool.py`, registry entry
- Input validation with Pydantic
- Token caching for API credentials
- Structured error handling
- Datadog tracing integration

### 6. Utilities (`/utils`)

Shared utilities and helpers:
- Logging utilities (structured JSON logging)
- Common helpers
- Configuration utilities

## Data Flow

### Typical Chat Message Flow

```
1. Client sends message to /v1/chat
                ↓
2. API validates request (Pydantic schema)
                ↓
3. Route handler calls message_service
                ↓
4. message_service orchestrates:
   - Retrieves conversation history (storage)
   - Loads agent configuration (agent_service)
   - Retrieves relevant memories (memory)
   - Retrieves relevant knowledge (knowledge/RAG)
                ↓
5. Agent processes message:
   - Generates response via LLM
   - May call tools for external data
   - Streams response chunks
                ↓
6. Response sent back to client (SSE for streaming)
                ↓
7. Background tasks:
   - Save message to database
   - Update user memory
   - Log analytics
```

### Tool Execution Flow

```
1. Agent determines tool use needed
                ↓
2. Tool registry provides tool instance
                ↓
3. Tool execution:
   - Retrieves integration credentials from DB
   - Calls external API (POS, reservation, etc.)
   - Handles errors and retries
                ↓
4. Tool returns structured result
                ↓
5. Agent incorporates result into response
```

## External Integrations

| Category | Service | Version | Purpose |
|----------|---------|---------|---------|
| **AI/ML** | OpenAI | v1.95.1 | GPT models (GPT-4, GPT-4o) |
| | Anthropic | v0.71.0 | Claude models |
| | Google GenAI | v1.25.0 | Gemini models |
| | Groq | v0.15.0 | Fast LLM inference |
| | mem0ai | v0.1.48 | Personalized memory |
| | LlamaIndex | v0.14.3 | RAG framework |
| | Pinecone | v7.3.0 | Vector database |
| | Cohere | - | Embeddings |
| | Instructor | v1.9.2 | Structured LLM outputs |
| **AWS** | Secrets Manager | boto3 v1.37.34 | Credential storage |
| | S3 | boto3 v1.37.34 | Asset storage |
| | EventBridge | boto3 v1.37.34 | Event-driven processing |
| | Bedrock | boto3 v1.37.34 | Content guardrails |
| **Communication** | Twilio | v9.3.2 | SMS and phone numbers |
| | VAPI | v1.6.0 | Voice AI platform |
| | Slack SDK | v3.33.5 | Internal notifications |
| **Business** | Stripe | v12 | Payment and subscriptions |
| | Shopify API | v12.7.0 | E-commerce integration |
| | Toast | - | POS system |
| | Square | - | POS system |
| | Adora | - | POS system |
| | OLO | - | Online ordering |
| | MenuSifu | - | POS system |
| | OpenTable | - | Reservations |
| | Resy | - | Reservations |
| | Yelp | - | Reservations |
| **Observability** | Datadog | v0.52.0 | Metrics, tracing, logging |
| | ddtrace | v3.11.0 | Distributed tracing |
| | Datadog LLM Obs | - | AI-specific monitoring |
| **Database** | PostgreSQL | - | Primary database |
| | pgvector | v0.3.2 | Vector extension |
| | SQLAlchemy | v2.0.32 | ORM |
| | Alembic | v1.13.2 | Migrations |
| | asyncpg | v0.30.0 | Async driver |
| **Web** | FastAPI | v0.120.2 | Web framework |
| | Uvicorn | v0.30.6 | ASGI server |
| | Pydantic | v2.11.7 | Data validation |
| | httpx | v0.28.1 | HTTP client |

## Configuration Management

### Environment Strategy

Four environments with progressive promotion:
- **dev** (local) - Local development with Docker
- **lat** (latest) - Latest automated deployments
- **stg** (staging) - Pre-production testing
- **prd** (production) - Live system

### Configuration Sources

1. **Environment Variables** - Runtime configuration
2. **AWS Secrets Manager** (production) - Sensitive credentials
3. **Local Environment File** (development) - `local.env` (see docker-compose.yml)

### Configuration Classes

Pydantic Settings for type-safe configuration:
- `ApiSettings` - API server configuration
- `DbSettings` - Database connection parameters
- Agent configuration classes - Comprehensive agent settings

## Async Processing Patterns

### Real-Time Streaming
- **Server-Sent Events (SSE)** for chat streaming
- Async generators with proper cleanup
- Token-by-token streaming from LLMs

### Background Tasks
- **FastAPI Background Tasks** - Fire-and-forget processing
- **asyncio.create_task()** - Detached async execution
- Memory updates in background to avoid blocking

### Event-Driven
- **AWS EventBridge** - Decoupled event handling (catering)
- No traditional task queue (no Celery)

### Caching
- In-memory caching with TTL (5-minute for memories)
- Token caching for API integrations
- Thread-safe cache implementation

## Deployment Architecture

### Local Development (Docker)
```
┌─────────────────────────────────────┐
│  Host Machine                        │
│  - Source code                       │
│  - Docker Compose                    │
└─────────────────────────────────────┘
         │
         ├──► Docker Container: API
         │    - FastAPI (port 8000)
         │    - Python 3.11-slim
         │    - Hot reload enabled
         │
         └──► Docker Container: Database
              - PostgreSQL + pgvector (port 5432)
              - Persistent volume
```

### Production (AWS)
- Containerized deployment
- RDS PostgreSQL with pgvector
- Secrets Manager for credentials
- S3 for assets
- EventBridge for async workflows
- CloudWatch for logging

## Design Patterns

### Architectural Patterns
- **Repository Pattern** - Data access abstraction
- **Service Layer** - Business logic separation
- **Dependency Injection** - FastAPI Depends()
- **Factory Pattern** - Agent and model creation
- **Strategy Pattern** - Multiple LLM providers

### Best Practices
- **Async-First** - Full async/await throughout
- **Type Safety** - Complete type hints with pyright
- **Separation of Concerns** - Clear layer boundaries
- **DRY Principle** - Shared utilities and base classes
- **RESTful API Design** - Standard HTTP methods and status codes

## Security Considerations

### Credential Management
- AWS Secrets Manager in production
- No credentials in code or version control
- Separate client and server secrets

### API Security
- CORS configuration by environment
- Request validation with Pydantic
- Content guardrails (AWS Bedrock)

### Data Security
- Encrypted database connections
- Secure token storage
- Audit trail via change_log table

## Testing Strategy

### Testing Framework
- **pytest** (v8.3.2) - Test runner
- **pytest-cov** (v6.0.0) - Coverage reporting
- **pytest-mock** (v3.14.0) - Mocking

### Code Quality
- **black** (v24.8.0) - Code formatting
- **isort** (v5.13.2) - Import sorting
- **ruff** (v0.6.2) - Fast linting
- **pyright** (v1.1.382) - Type checking

### CI/CD
- Pre-commit hooks for local validation
- GitHub Actions for automated testing
- Database migration validation
- Build and release workflows

## Performance Characteristics

### Database
- Connection pooling (30 connections, 50 overflow)
- Async queries for non-blocking I/O
- Indexed queries via SQLAlchemy

### API
- Async request handling
- Streaming responses to reduce latency
- Background task execution

### Caching
- Memory caching with TTL
- Token caching for external APIs
- Cache warming in background

### Monitoring
- Datadog APM for tracing
- LLM observability for AI metrics
- Structured logging for debugging

## Key Files Quick Reference

| Purpose | File Path | Description |
|---------|-----------|-------------|
| **Entry Points** | | |
| API Server | `/api/main.py` | FastAPI app factory |
| AI Agent | `/agent/agent.py` | Main agent orchestration |
| Agent Config | `/agent/config.py` | Agent configuration models |
| **API Layer** | | |
| Chat Routes | `/api/routes/v1/chat.py` | Chat endpoint handlers |
| Admin Routes | `/api/routes/v1/admin.py` | Admin CRUD endpoints |
| Integration Routes | `/api/routes/v1/integrations.py` | Integration endpoints |
| API Schemas | `/api/schemas/` | Pydantic request/response models |
| API Settings | `/api/settings.py` | API configuration |
| **Agent Components** | | |
| Agent Framework | `/agent/framework/agno.py` | Agent framework wrapper |
| Model Layer | `/agent/model/` | LLM provider abstraction |
| Memory System | `/agent/memory/` | mem0ai integration |
| Knowledge/RAG | `/agent/knowledge/` | LlamaIndex + Pinecone |
| Tool Management | `/agent/tool/` | Tool loading and execution |
| Storage | `/agent/storage/` | Conversation history |
| Guardrails | `/agent/guardrails/` | Content safety |
| **Services** | | |
| Message Service | `/services/message_service/` | Core message processing |
| Agent Service | `/services/agent_service/` | Agent management |
| Account Service | `/services/account_service/` | Account management |
| Integration Service | `/services/integration_service/` | Integration management |
| **Database** | | |
| Tables | `/db/tables/` | SQLAlchemy models (29 tables) |
| Repositories | `/db/repositories/` | Data access layer (25 repos) |
| Migrations | `/db/migrations/versions/` | Alembic migrations |
| DB Settings | `/db/settings.py` | Database configuration |
| Migration Config | `/db/alembic.ini` | Alembic configuration |
| **Tools** | | |
| Tool Registry | `/tools/registry.py` | Central tool registration |
| Tool Standards | `/tools/TOOL_STANDARDS.md` | Tool development guide |
| Toast Tool | `/tools/toast_tool/` | Toast POS integration |
| Square Tool | `/tools/square_tool/` | Square POS integration |
| OpenTable Tool | `/tools/opentable_tool/` | OpenTable integration |
| Resy Tool | `/tools/resy_tool/` | Resy integration |
| **Configuration** | | |
| Dependencies | `/pyproject.toml` | Dev tool configuration |
| Requirements | `/requirements.txt` | Production dependencies |
| Environment File | `/local.env` | Local environment variables |
| Docker Compose | `/docker-compose.yml` | Local development setup |
| **Scripts** | | |
| Install Script | `/scripts/install.sh` | Dependency installation |
| Validation Script | `/scripts/validate.sh` | Code quality checks |
| **CI/CD** | | |
| Pre-commit | `/.github/workflows/precommit.yml` | Pre-commit validation |
| DB Migration Check | `/.github/workflows/check-db-migration.yml` | Migration validation |
| Build Workflow | `/.github/workflows/create-build.yml` | Build process |
| **Documentation** | | |
| Project Guide | `/CLAUDE.md` | High-level project instructions |
| Architecture | `/.claude/docs/architecture.md` | This file |
| Logging Guide | `/utils/CLAUDE.md` | Logging guidelines |

## Future Considerations

### Scalability
- Current architecture is monolithic
- Consider service decomposition for scale
- Event-driven architecture already in place (EventBridge)

### Observability
- Comprehensive Datadog integration
- LLM-specific observability
- Structured logging throughout

### Extensibility
- Tool registry allows easy addition of new tools
- Multi-provider LLM support
- Plugin-style service architecture
