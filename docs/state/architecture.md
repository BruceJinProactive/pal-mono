# Architecture Overview

> **Last updated:** 2026-06-19

## Quick Reference

**System Type**: Multi-tenant conversational AI platform for restaurant/food service
**Primary Language**: Python >=3.11,<3.14
**Web Framework**: FastAPI (async)
**Database**: PostgreSQL + pgvector
**AI Frameworks**: Agno + pal-agents (v0.2.185)
**Voice Platform**: LiveKit
**Architecture Style**: Monolithic with event-driven components
**Deployment**: Docker (local), AWS (production)

**Key Metrics**:
- 48 database tables
- 57 repository classes
- 48 business services
- 17 registered AI agent tools
- 9 API route groups
- 4 environments (dev/lat/stg/prd)

**Entry Points**:
- API: `/api/main.py` → FastAPI app
- Agent: `/agent/agent.py` → AI orchestration
- Database: `/db/tables/` → SQLAlchemy models
- Events: `/events/` → EventBridge integration

## System Overview

pal-mono is a multi-tenant conversational AI platform designed for restaurant and food service businesses. It provides AI-powered agents that can handle customer interactions across multiple channels (voice, SMS, web chat) while integrating with POS systems, reservation platforms, and other business tools. The system uses LiveKit (agent-worker) as its voice platform.

## High-Level Architecture

```text
┌─────────────────────────────────────────────────────────────────┐
│                         Client Layer                             │
│  (Web Chat, SMS via Twilio, Voice via LiveKit, API Clients)     │
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
│  - 48 Business Services (account, agent, message, integration) │
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
- `/v1/integrations` - Third-party integrations (Adora, Folk, OLO, Slack, Square, Stripe, Toast, Twilio)
- `/v1/assets` - Asset management (S3-backed)
- `/v1/operation` - Checklists, monitoring, routines, signal sources, video upload
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
           │    - Langfuse LLM observability
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
- Voice settings (LiveKit integration)
- Transcription configuration

**Additional Framework**: `pal-agents` (v0.2.185) — a separate agent framework (`PalAgent` with `Spec` and `RuntimeContext`) used alongside Agno, particularly for LiveKit voice agent workers.

### 3. Service Layer (`/services`)

47 specialized services implementing business logic:

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
| `voice_service` | Communication | Voice call handling (LiveKit) |
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

`GET /accounts/{account_name}/state-change-events` returns state-change events
matching the account, optional project/entity filters, and observed-at time
window. The endpoint defaults `start` to the past 24 hours when omitted and
paginates returned rows with `page` (default `1`) and `limit` (default `100`,
max `1000`); `total` reports the full filtered match count before pagination.
`GET /accounts/{account_name}/state-change-events/{event_id}` accepts
`include_video` (default `false`). When requested, the response includes
nullable `video_url`; the service first uses `event_metadata.video_url` when it
contains a video asset URI, otherwise it derives the matching one-minute video
from `frame_s3_key` by replacing `/images/` with `/videos/` and flooring the
timestamped image filename to `YYYY-MM-DD_HH-MM-00.mp4`.

Vision state-change events also drive lightweight rule workflows in
`services/vision_observation_service/_workflow.py`. Each workflow is selected by
`vision_rule.type` and owns its entity-type, optional state-definition type, and
transition validation. Current workflows cover `table_cleanness`,
`table_occupied`, `table_touch`, `glove_usage`, `food_container_on_ground`,
`manager_in_room`, `staff_at_front_desk`, `guest_visiting_menu_board`, and
`empty_tray`. Matched workflows write linked
`vision_rule_event` rows through the repository layer. Test events marked with
`event_metadata.is_test == True` are persisted as state changes but skipped by
rule workflows. Rules can carry empty-default text-array `label` values, and
the vision-rule CRUD API returns them on rule responses. `PATCH
/accounts/{account_name}/vision-rules/{rule_id}` treats omitted `label` as
unchanged and a provided list, including `[]`, as the replacement value.
`rule_metadata` follows the same update contract: omitted metadata is unchanged,
and a provided object replaces the previous metadata object so callers can
remove old keys.
`GET /accounts/{account_name}/vision-rules` also returns `items_by_label`,
grouping every rule under each label in its list; rules without labels appear
under `no-labeld`.
Rule events store a non-null fixed-scale numeric `duration` in minutes that
defaults to `0.0`. State-transition workflows set that duration to the elapsed
time spent in the prior state before the trigger state was observed. For example,
`table_cleanness` records how many minutes a table stayed `dirty` when it
transitions to `clean`; if no prior-state start time can be resolved, the event
keeps the `0.0` default. `GET /accounts/{account_name}/rule-events` returns all
rule events matching the account, optional rule/entity filters, and the time
window; it has no pagination or `limit` query parameter. `PATCH
/accounts/{account_name}/rule-events/{event_id}` is account-scoped and lets
authorized operations callers correct a rule event's `triggered_at` timestamp
and `duration` in minutes without changing the linked rule, entity, state-change
event, severity, or metadata.

Vision V2 observations derive `observed_at` from the image path when the
filename matches the UTC snapshot format `YYYY-MM-DD_HH-MM-SS.jpg`, including
paths like `snapshots/YYYY-MM-DD/YYYY-MM-DD_HH-MM-SS.jpg` and uploaded S3 keys
under `security/cameras/.../images/YYYY-MM-DD/`. If the filename does not carry
that format, Vision logs a warning and falls back to backend processing time.
The resolved `observed_at` is reused for entity current-state metadata,
state-change events, and downstream rule-event trigger time.

The `empty_tray` workflow matches `food_tray` entities transitioning from
`not_empty` to `empty` and uses the event's `definition_type` when resolving
prior-state duration. The `visionruletype` database enum also accepts
`people_queued_up` and `floor_cleanness` rule records for manage-app
configuration, but they do not have rule workflows yet.

Vision entities can track one current state per state-definition type. The
legacy `vision_entity.current_state_id` and `current_state_since` columns remain
for compatibility with single-state clients, but multi-state data is stored in
`vision_entity.metadata.current_states`, keyed by the state definition's
`definition_type`. Entity API responses expose that map as `current_states`
alongside the legacy fields. Observation prompts group active state definitions
by `definition_type`, state-change events include `event_metadata.definition_type`,
and state-definition delete guards check both the legacy current-state column and
the metadata map before removing a state definition. Deleting one entity
current-state type uses the `definition_type` key and removes the metadata entry
even if its stored state UUID is malformed, so stale typed metadata can be
cleaned up without deleting the state definition itself.

Vision entities can track one current state per state-definition type. The
legacy `vision_entity.current_state_id` and `current_state_since` columns remain
for compatibility with single-state clients, but multi-state data is stored in
`vision_entity.metadata.current_states`, keyed by the state definition's
`definition_type`. Entity API responses expose that map as `current_states`
alongside the legacy fields. Observation prompts group active state definitions
by `definition_type`, state-change events include `event_metadata.definition_type`,
and state-definition delete guards check both the legacy current-state column and
the metadata map before removing a state definition.

### 4. Database Layer (`/db`)

**Technology**: PostgreSQL with pgvector extension

**Components**:
- `/db/tables/` - SQLAlchemy 2.0 table definitions (47 tables)
- `/db/repositories/` - Repository pattern for data access (56 repository classes)
- `/db/migrations/` - Alembic migrations

**Tables by Domain**:

*Core*: `accounts`, `agents`, `projects`, `users`, `account_user`, `user_invitation`, `contacts`, `project_contacts`

`projects` stores per-location lifecycle metadata. `status` uses the
`ProjectStatus` enum and is limited to `pending`, `onboarding`, and `live`.
`live_at` is a non-null timestamp for the location's live/start time; the
schema migration backfills existing rows from `created_at`, and new rows
default to `now()`.

*Agent & AI*: `agent_capabilities`, `capability_actions`, `prompts`, `voice_configs`

*Communication*: `conversations`, `messages`, `phone_calls`

`phone_calls` stores post-call voice analytics such as duration, latency,
ended reason, call purpose, user satisfaction, language, and transfer reason
classification. Transfer reason analysis is folded into the same post-call LLM
analytics pass as call purpose and satisfaction; `transfer_purpose` remains live
routing metadata on `conversations`.

*Transactions*: `orders`, `adora_orders`, `reservations`, `catering_requests`,
`catering_request_activities`

`catering_requests.status` uses the `RequestStatus` enum to track the
request lifecycle. Planned catering requests move through:
`LEAD` -> `PROPOSAL` -> `CONFIRMED` -> `LOCKED` -> `IN_PREPARATION` ->
`READY` -> `COMPLETED` -> `CLOSED`. `COMPLETED` means the catering request has
been operationally fulfilled, while `CLOSED` means the request is
administratively closed with no further action expected. Legacy status values
remain available for older rows and compatibility paths.

`catering_requests` supports partial lead capture: `event_date` and
`contact_phone_number` are nullable, and `contact_email` stores an optional
requester email directly on the request. This lets catering workflows track an
incomplete inquiry even when scheduling or phone details are not yet known.
Repository DTOs, service methods, agent catering persistence, and catering API
schemas accept and return these partial fields.

When a new request is created, the catering service snapshots customer history
into `prior_catering_request_count`, `prior_order_count`,
`last_catering_request_at`, and `last_order_at`. Catering request history is
matched across all projects in the same account by requester phone or requester
email; order history is matched across all projects in the same account by
phone. These are creation-time context fields, not live counters. The request
also stores nullable monetary planning fields: `estimated_order_value`,
`confirmed_order_value`, `deposit_requirement_value`, and
`deposit_received_value`.

The public catering request detail endpoint returns requester phone number,
requester email, and the project `address` as `store_address` for customer
confirmation pages, while still omitting project IDs, contact assignment,
idempotency keys, and internal
timestamps.

`catering_request_activities` stores an append-only timeline for each catering
request. Rows are scoped by `catering_request_id` and denormalized `project_id`,
with enum columns for activity type, actor type, and source, a stable
human-readable `description`, and JSONB `metadata` for event-specific payloads
such as changed fields, proposal snapshots, or SMS content. The table follows
the no-FK/no-relationship ADRs; referential integrity is enforced by repository
and service queries. The catering service records creation, update, and
status-change entries, and it verifies project ownership before listing a
request timeline. The project catering request list supports embedding recent
activity entries for the workflow page rather than exposing a standalone
activity-log URL.

*Business*: `campaigns`, `credit_grants`, `faqs`, `features`, `feedback`, `integration`, `lead`, `subscriptions`, `affiliates`

*Operations*: `checklists`, `checkpoints`, `checkpoint_runs`, `monitoring_configs`, `monitoring_runs`, `routines`, `routine_items`, `routine_item_responses`, `routine_executions`, `routine_schedules`, `routine_submissions`, `signal_feeds`, `signal_sources`

Vision event tables are time partitioned: `vision_state_change_event` by
`observed_at` and `vision_rule_event` by `triggered_at`. Both tables keep a
default partition (`vision_state_change_event_default` and
`vision_rule_event_default`) so event writes still succeed before date-specific
partitions are created.

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
| `livekit_tool` | Voice | LiveKit voice operations | `/tools/livekit_tool/` |
| `catering_tool` | Business | Catering requests | `/tools/catering_tool/` |

*Unregistered tool directories* (exist but not in registry):
- `sms_tool` - Send SMS via Twilio (`/tools/sms_tool/`)
- `escalation_tools` - Escalate to human (`/tools/escalation_tools/`)

**Tool Standards** (`/tools/CLAUDE.md`):
- Consistent structure: `__init__.py`, `_implementation.py`, `classes.py`, `_apis/`
- Inherit from `Toolkit` (agno.tools), init with `super().__init__(name="tool_name")`
- `@observe(as_type="tool")` decorator required for all methods (Langfuse tracing)
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
- `dd.py` - Observability utilities (Langfuse + OTel)
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
- OpenTelemetry for distributed tracing
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
| Folk Notion Sync Service | `/services/folk_notion_sync/` | Folk Pipeline Review deal/company webhook sync into Notion |
| Integration Service | `/services/integration_service/` | Integration management |
| Monitoring Service | `/services/monitoring_service/` | Monitoring and LLM analysis |
| Notification Service | `/services/notification_service/` | Multi-channel notifications |
| Routine Service | `/services/routine_service/` | Routine management |
| **Database** | | |
| Tables | `/db/tables/` | SQLAlchemy models (47 tables) |
| Repositories | `/db/repositories/` | Data access layer (56 repo classes) |
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
| Architecture | `docs/state/architecture.md` | This file |
| API Routes Guide | `/api/routes/CLAUDE.md` | Route development patterns |
| Tool Standards | `/tools/CLAUDE.md` | Tool development guide |

## Future Considerations

### Scalability
- Current architecture is monolithic
- Consider service decomposition for scale
- Event-driven architecture already in place (EventBridge)

### Voice Platform
- LiveKit is the production voice platform (ADR-018)
- pal-agents framework for LiveKit agent workers
- See `docs/plans/livekit-migration/` for migration history

### Observability
- Langfuse + OpenTelemetry observability
- LLM-specific observability
- Structured logging throughout

### Extensibility
- Tool registry allows easy addition of new tools
- Multi-provider LLM support
- Plugin-style service architecture
- Capability-based prompt system (see `docs/records/2026-01-21-prompt-v2-capability-system.md`)
