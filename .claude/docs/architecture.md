# Architecture Overview

## Quick Reference

**System Type**: Multi-tenant conversational AI platform for restaurant/food service
**Primary Language**: Python >=3.11,<3.14
**Web Framework**: FastAPI (async)
**Database**: PostgreSQL + pgvector
**AI Frameworks**: Agno (v1.7.6) + pal-agents (v0.2.113)
**Voice Platforms**: VAPI (v1.6.0) + LiveKit (>=1.0.0)
**Architecture Style**: Monolithic with event-driven components
**Deployment**: Docker (local), AWS (production)

**Key Metrics**:
- 47 database tables
- 43 repository classes
- 45 business services
- 17 registered AI agent tools (19 tool directories)
- 9 API route groups
- 4 environments (dev/lat/stg/prd)

**Entry Points**:
- API: `/api/main.py` → FastAPI app
- Agent: `/agent/agent.py` → AI orchestration
- Database: `/db/tables/` → SQLAlchemy models
- Events: `/events/` → EventBridge integration

## System Overview

pal-mono is a multi-tenant conversational AI platform designed for restaurant and food service businesses. It provides AI-powered agents that can handle customer interactions across multiple channels (voice, SMS, web chat) while integrating with POS systems, reservation platforms, and other business tools. The system supports both VAPI (webhook-driven) and LiveKit (agent-worker) voice platforms.

## High-Level Architecture

```text
┌─────────────────────────────────────────────────────────────────┐
│                         Client Layer                             │
│  (Web Chat, SMS via Twilio, Voice via VAPI/LiveKit, API Clients)│
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI Application                         │
│  - REST API Endpoints (/v1/admin, /v1/chat, /v1/integrations)  │
│  - Internal APIs (/v1/internal - monitoring, routines, events) │
│  - Request Validation (Pydantic)                                │
│  - CORS & Middleware                                            │
│  - RBAC Authorization                                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Service Layer                              │
│  - 45 Business Services (account, agent, message, integration) │
│  - Business Logic & Orchestration                               │
│  - Transaction Management                                       │
│  - Monitoring, Routines, Notifications                          │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
    │ Agent System │  │   Database   │  │ External APIs│
    │ (Agno +      │  │  (Postgres + │  │ & Services   │
    │  pal-agents) │  │   pgvector)  │  │              │
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
| **Events** | AWS EventBridge | Services | Async event-driven communication |
| **Auth** | Cognito, RBAC tables | API Routes | Authentication & authorization |

**Key Data Flow**:
1. Client → API Routes → Services → Repositories → Database
2. Client → API Routes → message_service → Agent → LLM/Tools/Memory/Knowledge
3. Agent → Tools → External APIs (POS, reservations, etc.)
4. Services → EventBridge → Async handlers (catering, notifications)

## Core Components

### 1. API Layer (`/api`)

**Technology**: FastAPI with async/await support

**Structure**:
- `/api/main.py` - Application factory with lifespan management
- `/api/routes/` - REST endpoint definitions organized by domain
- `/api/routes/v1_router.py` - Root router aggregating all domain routers
- `/api/routes/endpoints.py` - Centralized endpoint path constants
- `/api/schemas/` - Pydantic models for request/response validation

**Route Groups** (9 routers in `/v1`):
- `/v1/admin` - Account, agent, project, user, team, billing, capabilities management (29 sub-modules)
- `/v1/chat` - Main conversational interface (streaming and non-streaming, OpenAI-compatible completions)
- `/v1/integrations` - Third-party integrations (Adora, OLO, Shopify, Slack, Square, Stripe, Toast, Twilio, VAPI)
- `/v1/assets` - Asset management (S3-backed)
- `/v1/operation` - Checklists, checkpoints, monitoring, routines, signal sources, video upload
- `/v1/catering` - Catering request handling
- `/v1/telephony` - Twilio telephony webhooks
- `/v1/internal` - Internal APIs (monitoring, routines, events, catering, voice/LiveKit)
- `/v1/health` & `/v1/ping` - Health check endpoints

**Features**:
- Environment-based CORS configuration
- Automatic OpenAPI documentation at `/docs`
- Request validation with Pydantic
- Async request handling throughout
- RBAC-based authorization via `require_account_permission` / `require_project_permission`

### 2. Agent System (`/agent`)

The core AI agent implementation providing conversational capabilities.

**Architecture**:

```text
┌─────────────────────────────────────────────────────────────┐
│                      Agent (agent.py)                        │
│  - Orchestrates conversation flow                            │
│  - Manages streaming and non-streaming responses             │
│  - Coordinates all submodules                                │
└─────────────────────────────────────────────────────────────┘
           │
           ├──► Framework (framework/agno.py)
           │    - Agno agent wrapper with streaming support
           │    - Streaming with filler words (internal/filler_words_manager.py)
           │    - Datadog LLM observability
           │    - Additional framework classes (classes.py)
           │
           ├──► Model (model/)
           │    - Multi-provider support (OpenAI, Anthropic, Google, Groq)
           │    - Model abstraction layer
           │
           ├──► Memory (memory/)
           │    - mem0ai integration for personalized memory
           │    - TTL cache
           │    - Background async updates
           │
           ├──► Knowledge (knowledge/)
           │    - LlamaIndex + Pinecone for RAG
           │    - Cohere embeddings
           │    - Integration-specific knowledge bases
           │
           ├──► Tool (tool/)
           │    - Dynamic tool loading via ToolRegistry
           │    - 17 registered specialized tools
           │    - Internal tool utilities
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
- Voice settings (VAPI and LiveKit integration)
- Transcription configuration

**Additional Framework**: `pal-agents` (v0.2.113) — a separate agent framework (`PalAgent` with `Spec` and `RuntimeContext`) used alongside Agno, particularly for LiveKit voice agent workers.

### 3. Service Layer (`/services`)

45 specialized services implementing business logic:

| Service | Category | Purpose |
|---------|----------|---------|
| `account_service` | Core | Multi-tenant account management |
| `admin_service` | Core | Admin operations and orchestration |
| `agent_service` | Core | Agent configuration and lifecycle |
| `auth_service` | Core | Authentication, RBAC, and permission management |
| `project_service` | Core | Project management (account + agent) |
| `team_service` | Core | Team management |
| `user_service` | Core | User authentication and management |
| `email_service` | Communication | Email notifications |
| `message_service` | Communication | Message processing (streaming/non-streaming/relay) |
| `notification_service` | Communication | Multi-channel notification orchestration (email/SMS) |
| `postmark_service` | Communication | Postmark email delivery |
| `realtime_service` | Communication | Realtime capabilities (WebSocket) |
| `relay_service` | Communication | External message relay |
| `voice_service` | Communication | Voice call handling (VAPI + LiveKit) |
| `integration_service` | Integration | Third-party integration management |
| `knowledge_service` | Integration | Integration-specific knowledge bases |
| `menu_service` | Integration | Menu management |
| `analytics_service` | Business | Usage analytics |
| `asset_service` | Business | Asset storage (S3) |
| `campaign_service` | Business | Marketing campaigns |
| `capability_service` | Business | Agent capability management |
| `catering_service` | Business | Catering workflow (EventBridge) |
| `faq_service` | Business | FAQ management |
| `features_service` | Business | Feature management |
| `feedback_service` | Business | User feedback collection |
| `prompt_service` | Business | Prompt templates |
| `reservation_service` | Business | Reservation management |
| `rewardful_service` | Business | Affiliate/referral rewards |
| `subscription_service` | Business | Stripe billing management |
| `terms_service` | Business | Terms of service management |
| `checklist_service` | Operations | Operational checklists |
| `checkpoint_service` | Operations | Quality review checkpoints |
| `monitoring_service` | Operations | Monitoring configuration and LLM-powered analysis |
| `routine_service` | Operations | Routine definitions |
| `routine_execution_service` | Operations | Routine execution tracking |
| `routine_schedule_service` | Operations | Routine scheduling |
| `routine_submission_service` | Operations | Routine submission processing |
| `signal_source_service` | Operations | Signal source management |
| `transaction_service` | Operations | Transaction tracking (orders, reservations) |
| `vision_service` | Operations | Image/video processing |
| `google_maps_service` | External | Google Maps integration |
| `history_service` | External | History management |
| `notion_service` | External | Notion integration |
| `number_service` | External | Phone number management |
| `slack_service` | External | Slack notifications |

### 4. Database Layer (`/db`)

**Technology**: PostgreSQL with pgvector extension

**Components**:
- `/db/tables/` - SQLAlchemy 2.0 table definitions (47 tables)
- `/db/repositories/` - Repository pattern for data access (43 repositories)
- `/db/migrations/` - Alembic migrations

**Tables by Domain**:

*Core*: `accounts`, `agents`, `projects`, `users`, `account_user`, `user_invitation`, `contacts`, `project_contacts`

*Agent & AI*: `agent_capabilities`, `capability_actions`, `prompts`, `voice_configs`

*Communication*: `conversations`, `messages`, `phonecalls`

*Transactions*: `orders`, `adora_orders`, `reservations`, `catering_requests`

*Business*: `campaigns`, `credit_grants`, `faqs`, `features`, `feedback`, `integration`, `lead`, `subscriptions`, `affiliates`

*Operations*: `checklists`, `checkpoints`, `checkpoint_runs`, `monitoring_configs`, `monitoring_runs`, `routines`, `routine_items`, `routine_item_responses`, `routine_executions`, `routine_schedules`, `routine_submissions`, `signal_feeds`, `signal_sources`

*Auth & Security*: `permission`, `role_permission`, `resource_role_assignment`, `tos_acceptance`

*System*: `change_log`, `onboarding_webhook_event`

**Connection Management**:
- Async connection pooling (30 connections, 50 max overflow)
- Both sync and async session support
- Transaction management with proper rollback

### 5. Tools System (`/tools`)

17 registered tools in the ToolRegistry that extend agent capabilities:

| Tool | Category | Purpose | File Path |
|------|----------|---------|-----------|
| `toast_tool` | POS | Toast POS operations | `/tools/toast_tool/` |
| `square_tool` | POS | Square POS operations | `/tools/square_tool/` |
| `adora_tool` | POS | Adora POS operations | `/tools/adora_tool/` |
| `adora_v2_tool` | POS | Adora POS v2 operations | `/tools/adora_v2_tool/` |
| `olo_tool` | POS | OLO ordering | `/tools/olo_tool/` |
| `menusifu_tool` | POS | MenuSifu POS operations | `/tools/menusifu_tool/` |
| `opentable_tool` | Reservation | OpenTable bookings | `/tools/opentable_tool/` |
| `resy_tool` | Reservation | Resy bookings | `/tools/resy_tool/` |
| `resy_tool_with_reservation` | Reservation | Resy with existing reservation | `/tools/resy_tool_with_reservation/` |
| `yelp_tool` | Reservation | Yelp bookings | `/tools/yelp_tool/` |
| `yelp_credit_card_tool` | Reservation | Yelp with credit card | `/tools/yelp_credit_card_tool/` |
| `yelp_no_credit_card_tool` | Reservation | Yelp without credit card | `/tools/yelp_no_credit_card_tool/` |
| `minitable_tool` | Reservation | MiniTable bookings | `/tools/minitable_tool/` |
| `store_messaging_tool` | Communication | Store messaging | `/tools/store_messaging_tool/` |
| `vapi_tool` | Communication | VAPI voice integration | `/tools/vapi_tool/` |
| `livekit_transfer_tool` | Communication | LiveKit call transfer | `/tools/livekit_transfer_tool/` |
| `catering_tool` | Business | Catering requests | `/tools/catering_tool/` |

*Unregistered tool directories* (exist but not in registry):
- `sms_tool` - Send SMS via Twilio (`/tools/sms_tool/`)
- `escalation_tools` - Escalate to human (`/tools/escalation_tools/`)

**Tool Standards** (`/tools/CLAUDE.md`):
- Consistent structure: `__init__.py`, `_implementation.py`, `classes.py`, `_apis/`
- Inherit from `Toolkit` (agno.tools), init with `super().__init__(name="tool_name")`
- `@tool` decorator required for all methods (Datadog tracing)
- `@params_validate()` required only for methods with parameters
- Input validation with Pydantic
- Token caching for API credentials
- Register all tools in `tools/registry.py`

### 6. Events System (`/events`)

AWS EventBridge integration for asynchronous event-driven communication.

**Components**:
- `/events/_eventbridge.py` - EventBridge client and publishing
- `/events/schema.py` - Event schema definitions

### 7. Utilities (`/utils`)

Shared utilities and helpers:
- `log.py` - Logging utilities (structured JSON logging)
- `dd.py` - Datadog utilities
- `request_context.py` - Request context management
- `secret.py` - AWS Secrets Manager integration

## Data Flow

### Typical Chat Message Flow

```text
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

```text
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
- **AWS EventBridge** - Decoupled event handling (catering, notifications, billing)
- No traditional task queue (no Celery)

### Caching
- In-memory caching with TTL (for memories)
- Token caching for API integrations
- Thread-safe cache implementation

## Deployment Architecture

### Local Development (Docker)
```text
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
- **RBAC** - Role-based access control with permissions, roles, and resource assignments

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
- RBAC authorization (permissions, roles, resource assignments)

### Data Security
- Encrypted database connections
- Secure token storage
- Audit trail via change_log table
- Terms of service acceptance tracking

## Testing Strategy

### Testing Framework
- **pytest** (v8.3.2) - Test runner
- **pytest-cov** (v6.0.0) - Coverage reporting
- **pytest-mock** (v3.14.0) - Mocking
- **pytest-asyncio** (v0.24.0) - Async test support
- **diff-cover** (v9.2.4) - Incremental coverage enforcement

### Code Quality
- **black** (~v24.8.0) - Code formatting
- **isort** (~v5.13.2) - Import sorting
- **ruff** (~v0.6.2) - Fast linting
- **pyright** (~v1.1.382) - Type checking
- **import-linter** (~v2.2) - Architecture boundary enforcement
- **toml-sort** (~v0.24.2) - pyproject.toml formatting

### CI/CD
- Pre-commit hooks for local validation
- GitHub Actions workflows:
  - `precommit.yml` - Pre-commit validation
  - `check-db-migration.yml` - Database migration validation
  - `check-test-location.yml` - Test file location enforcement
  - `create-build.yml` - Build process
  - `create-release.yml` - Release process
  - `test-coverage.yml` - Test coverage reporting
  - `validate-db-schema-pr.yml` - DB schema validation on PRs
  - `validate-dependency-pr.yml` - Dependency validation on PRs
  - `validate-notion-link-pr.yml` - Notion link validation on PRs

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
| Event System | `/events/schema.py` | EventBridge event schemas |
| **API Layer** | | |
| V1 Router | `/api/routes/v1_router.py` | Root router aggregation |
| Endpoint Constants | `/api/routes/endpoints.py` | Centralized endpoint paths |
| Chat Routes | `/api/routes/chat/` | Chat endpoint handlers |
| Admin Routes | `/api/routes/admin/` | Admin CRUD endpoints (29 sub-modules) |
| Integration Routes | `/api/routes/integrations/` | Integration endpoints |
| Operation Routes | `/api/routes/operation/` | Operations endpoints |
| Internal Routes | `/api/routes/internal/` | Internal APIs |
| Telephony Routes | `/api/routes/telephony/` | Twilio webhooks |
| API Schemas | `/api/schemas/` | Pydantic request/response models |
| **Agent Components** | | |
| Agent Framework | `/agent/framework/agno.py` | Agno framework wrapper |
| Filler Words | `/agent/framework/internal/filler_words_manager.py` | Streaming filler words |
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
| Auth Service | `/services/auth_service/` | RBAC and permissions |
| Integration Service | `/services/integration_service/` | Integration management |
| Monitoring Service | `/services/monitoring_service/` | Monitoring and LLM analysis |
| Notification Service | `/services/notification_service/` | Multi-channel notifications |
| Routine Service | `/services/routine_service/` | Routine management |
| **Database** | | |
| Tables | `/db/tables/` | SQLAlchemy models (47 tables) |
| Repositories | `/db/repositories/` | Data access layer (43 repos) |
| Migrations | `/db/migrations/versions/` | Alembic migrations |
| DB Settings | `/db/settings.py` | Database configuration |
| Migration Config | `/db/alembic.ini` | Alembic configuration |
| **Tools** | | |
| Tool Registry | `/tools/registry.py` | Central tool registration (17 tools) |
| Tool Standards | `/tools/CLAUDE.md` | Tool development guide |
| Toast Tool | `/tools/toast_tool/` | Toast POS integration |
| Square Tool | `/tools/square_tool/` | Square POS integration |
| OpenTable Tool | `/tools/opentable_tool/` | OpenTable integration |
| Resy Tool | `/tools/resy_tool/` | Resy integration |
| LiveKit Transfer | `/tools/livekit_transfer_tool/` | LiveKit call transfer |
| **Configuration** | | |
| Dependencies | `/pyproject.toml` | Dev tool configuration |
| Environment File | `/local.env` | Local environment variables |
| Docker Compose | `/docker-compose.yml` | Local development setup |
| **Scripts** | | |
| Install Script | `/scripts/install.sh` | Dependency installation |
| Validation Script | `/scripts/validate.sh` | Code quality checks |
| **CI/CD** | | |
| Pre-commit | `/.github/workflows/precommit.yml` | Pre-commit validation |
| DB Migration Check | `/.github/workflows/check-db-migration.yml` | Migration validation |
| Build Workflow | `/.github/workflows/create-build.yml` | Build process |
| Release Workflow | `/.github/workflows/create-release.yml` | Release process |
| Test Coverage | `/.github/workflows/test-coverage.yml` | Coverage reporting |
| **Documentation** | | |
| Project Guide | `/CLAUDE.md` | High-level project instructions |
| Architecture | `/.claude/docs/architecture.md` | This file |
| API Routes Guide | `/api/routes/CLAUDE.md` | Route development patterns |
| Tool Standards | `/tools/CLAUDE.md` | Tool development guide |
| Logging Guide | `/utils/CLAUDE.md` | Logging guidelines |

## Future Considerations

### Scalability
- Current architecture is monolithic
- Consider service decomposition for scale
- Event-driven architecture already in place (EventBridge)

### Voice Platform Migration
- VAPI (current production) → LiveKit (in progress)
- pal-agents framework for LiveKit agent workers
- See `/.claude/docs/livekit-migration/` for detailed migration plans

### Observability
- Comprehensive Datadog integration
- LLM-specific observability
- Structured logging throughout

### Extensibility
- Tool registry allows easy addition of new tools
- Multi-provider LLM support
- Plugin-style service architecture
- Capability-based prompt system (see `/.claude/docs/prompts/promptv2-design.md`)
