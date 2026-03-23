# Testing Strategy for pal-mono

> **Status**: Proposed
> **Author**: Staff Engineer Assessment
> **Date**: 2026-03-23
> **Effort Ratio**: 8:2 (80% design thinking on integration tests, 20% on unit tests)

---

## Table of Contents

- [Part I: Current State Diagnosis](#part-i-current-state-diagnosis)
- [Part II: Integration Test Design (80% of effort)](#part-ii-integration-test-design-80-of-effort)
  - [II.A: Ten Scenarios](#iia--ten-scenarios)
  - [II.B: Fixture Architecture](#iib--fixture-architecture)
  - [II.C: System Invariants](#iic--system-invariants)
  - [II.D: Failure Injection](#iid--failure-injection)
- [Part III: Unit Tests (20% of effort)](#part-iii-unit-tests-20-of-effort)
- [Part IV: Implementation Sequence](#part-iv-implementation-sequence)
- [Part V: Anti-Patterns](#part-v-anti-patterns)
- [Appendix A: Current State Numbers](#appendix-a-current-state-numbers)
- [Appendix B: ADR Constraints](#appendix-b-adr-constraints)
- [Appendix C: Coverage Strategy](#appendix-c-coverage-strategy)

---

## Part I: Current State Diagnosis

### Not a coverage problem — a fidelity problem

The current 83-file, 1345-test suite doesn't lack quantity. It lacks fidelity. Consider:

- `test_account_repository.py` mocks `session.query().filter().filter().all()` — validates a call chain, not SQL correctness. Rename a column? Tests pass. Wrong `WHERE` clause? Tests pass.
- `test_authorization.py` mocks the DB session — RBAC tests pass even if the `resource_role_assignment` table schema is wrong.
- `test_get_chat_response_stream.py` shims `ddtrace`, `pal_agents`, and `livekit` via `sys.modules` injection — the test can't even import the real code without breaking.

**The diagnosis**: the suite tests *call sequences*, not *outcomes*. Bugs at integration seams — the thing that actually kills production — are invisible. The March 2026 DB pool exhaustion was caught by production monitoring, not tests, because no test exercised a real streaming DB session lifecycle.

The fix isn't "more tests." It's **differently-designed tests** — ones that exercise real code paths through real infrastructure.

### The 8:2 effort ratio

This ratio means where to put the **design thinking**, not test counts:

| | Integration Tests | Unit Tests |
|---|---|---|
| **Design thinking** | 80% | 20% |
| **Infrastructure investment** | Heavy (fixtures, factories, DB lifecycle, mock boundaries) | Light (pytest parametrize, simple assertions) |
| **Per-test design effort** | High — each test is a carefully designed scenario covering a real user flow | Low — mechanical, one assertion per case |
| **What you agonize over** | "Is this testing real behavior? Where's the mock boundary? What state machine path am I exercising? What tenant isolation property am I proving?" | "Does this pure function return the right value for these inputs?" |

The actual test count will likely end up closer to 50:50 — because unit tests are cheap to write once the integration infrastructure exists. But the thinking budget is 80% integration.

### The mock boundary rule

**Mock at the network/process boundary. Never mock your own code in integration tests.**

```
+---------------------------------------------------------------+
|                     REAL (integration tests)                   |
|                                                                |
|   TestClient -> API Routes -> Services -> Repositories -> DB   |
|                                 |                              |
|                    FastAPI DI chain (Depends)                   |
|                    SQLAlchemy sessions (real)                   |
|                    PostgreSQL (Docker)                          |
+---------------------------------------------------------------+
                              |
                    ---- MOCK BOUNDARY ----
                              |
+---------------------------------------------------------------+
|                     MOCKED (always)                            |
|                                                                |
|   AWS: S3, EventBridge, Cognito, Secrets Manager, SES         |
|   LLMs: OpenAI, Anthropic, Google, Groq                       |
|   External: Stripe, Twilio, LiveKit, Toast, Square, Adora     |
|   Other: mem0, Pinecone, Postmark, Datadog, Slack             |
+---------------------------------------------------------------+
```

---

## Part II: Integration Test Design (80% of effort)

### II.A — Ten Scenarios

Ordered by **bugs-caught-per-test**. Each scenario is a multi-step flow through real code — not an endpoint assertion.

---

#### S1 — Tenant Isolation Under Concurrent Accounts

*Most catastrophic failure mode. No FK constraints (ADR-004) means this is pure application integrity.*

```
Setup:
  Account A  -> Project A1 -> Agent A1 -> User A_customer -> Conversation A_conv -> Messages A_msgs
  Account B  -> Project B1 -> Agent B1 -> User B_customer -> Conversation B_conv -> Messages B_msgs
  (Identical data shapes — same channel types, same message content patterns)

Actions & Assertions:
  FOR EACH repository method that takes account_id/project_id:
    Call with Account A's credentials -> returns ONLY Account A's data
    Call with Account B's credentials -> returns ONLY Account B's data
    Call with Account A's credentials targeting Account B's resource_id -> 404 (not 403)

Properties proven:
  For all entity in {project, agent, conversation, message, order, integration, routine}:
    query(entity, acct=A) INTERSECT query(entity, acct=B) = empty set

Failure injection:
  Corrupt one query's WHERE clause (remove account_id filter) -> verify the test CATCHES it
```

**Why S1**: A tenant data leak is an existential business risk. This test is the canary — if it ever fails, deployment must halt. Every other test assumes this passes.

---

#### S2 — SSE Streaming Session Lifecycle (ADR-019)

*This already caused a production outage. A regression test would have caught it pre-deploy.*

```
Setup:
  World (account + project + agent + user)
  Mock LLM to return 5 chunks then [DONE]

Happy path:
  POST /v1/chat/ with stream=True via httpx.AsyncClient
  Collect SSE events
  Assert: N data events received, final event contains [DONE]
  Assert: Message record persisted in DB with complete content
  Assert: Conversation exists, status=ACTIVE
  Assert: DB connection pool.checkedout() == 0  (session returned)

Mid-stream failure:
  Mock LLM to yield 2 chunks then raise asyncio.TimeoutError
  Assert: error event in SSE stream (not silent truncation)
  Assert: DB session rolled back (no partial message record, or message has error status)
  Assert: pool.checkedout() == 0 (no leaked connection)

Client disconnect:
  Start streaming, read 2 events, close connection
  Wait 1s for cleanup
  Assert: pool.checkedout() == 0 (generator cleaned up)

Session ownership:
  Verify chat.py and chat_completions.py use AsyncSessionLocal() inside generator
  NOT Depends(get_db_async) — ADR-019
```

**Why S2**: The streaming path is the #1 traffic flow. The session ownership pattern is subtle and already broke once.

---

#### S3 — First Conversation: End-to-End Chat Flow

*Full stack tracer — catches missing filters, bad defaults, orphaned records.*

```
Setup:
  World with project bound to channel_identifier "+15551234567"
  Mock LLM to return "Welcome to our restaurant!"

Action:
  POST /v1/chat/ with project_name matching the channel_identifier

Assertions:
  1. Response contains agent's reply
  2. User record created (looked up by channel_identifier)
  3. Conversation record created (status=ACTIVE, correct project_id, correct user_id)
  4. Two Message records: user's input + agent's response
  5. Messages have correct conversation_id, correct body structure
  6. Conversation reuse: send second message within 2h -> SAME conversation_id
  7. Conversation expiry: send message after 24h -> NEW conversation_id, old one EXPIRED

Properties:
  message.conversation.project.account_id == original account_id (tenant chain intact)
  conversation.created_at monotonically increases across new conversations
```

**Why S3**: Traces the single most important code path. If this works, the core product works.

---

#### S4 — RBAC: Authorization with Zero Side Effects

*Tests that permission denial is atomic — no partial writes before the 403.*

```
Setup:
  World with owner (full permissions) and viewer (read-only)

Scenarios:
  viewer calls DELETE /accounts/{name} -> 403, account still exists
  viewer calls POST /agents -> 403, no agent created
  viewer calls PATCH /projects/{id} -> 403, project unchanged

  owner calls all of the above -> success

  staff on Project A calls GET /projects/{B_id} -> 404
  staff on Project A calls GET /projects/{A_id} -> 200

Properties:
  For all mutating_endpoint, unauthorized_user:
    call(endpoint, unauthorized_user) -> 403 AND db_state_unchanged()

  This means: snapshot DB state before call, compare after 403, assert identical.

Hierarchical RBAC:
  Assign role on Account -> verify project access inherits
  Assign role on Project -> verify routine/execution access inherits
```

**Why S4**: The existing test mocks the DB, so it can't catch a real RBAC query returning wrong results.

---

#### S5 — Stripe Webhook Idempotency & Ordering

*Webhooks are inherently unreliable — tests must prove resilience.*

```
Setup:
  World with active account + Stripe customer_id

Idempotency:
  POST /integrations/stripe/webhook with invoice.payment_succeeded (valid signature)
  POST same event again (same event_id)
  Assert: exactly 1 subscription state change, no duplicate records

Out-of-order:
  POST subscription.updated BEFORE subscription.created
  Assert: handled gracefully (no 500, logged warning)
  POST subscription.created
  Assert: final state is correct

Payment failure flow:
  POST invoice.payment_failed -> account status updates appropriately
  POST invoice.payment_succeeded -> account status recovers

Properties:
  For all webhook_event: deliver(event) . deliver(event) == deliver(event)  (idempotent)
  final_state independent of delivery order
```

---

#### S6 — POS Tool Credential Isolation (ADR-005)

*Tools bypass the service layer and access repos directly. Credential isolation is app-level.*

```
Setup:
  Account with 2 projects:
    Project A (Toast integration, cred_A)
    Project B (Square integration, cred_B)
  Mock Toast API and Square API via respx

Action:
  Agent for Project A receives "what's the menu?" -> invokes toast_tool

Assertions:
  toast_tool used cred_A (not cred_B, not Account-level creds)
  toast_tool's ProjectIntegration query filtered by project_id=A
  Square API was NOT called (wrong tool for this project)

Failure injection:
  Mock Toast API to return 500
  Assert: agent produces graceful response, not a crash
  Assert: conversation not stuck in broken state
```

---

#### S7 — Cross-Project Conversation Isolation (Same Account)

*Multi-location restaurant: Location 1's conversations must not leak into Location 2's agent context.*

```
Setup:
  1 Account, 2 Projects (Location 1 and Location 2), 1 Agent each
  5 messages in Location 1's conversation
  5 messages in Location 2's conversation

Action:
  New message to Location 2's agent

Assertions:
  Agent context (history loaded by query_history_messages) contains ONLY Location 2's messages
  Location 1's messages never appear in any agent input
```

---

#### S8 — Voice Call Lifecycle (LiveKit)

```
Setup:
  World with voice-enabled project (LiveKit SIP config)
  Mock LiveKit API

Flow:
  POST /internal/voice/init -> creates PhoneCall + Conversation
  Streaming chat -> messages persisted
  POST /internal/voice/end-call -> PhoneCall updated (duration, ended_reason), Conversation closed
  POST /internal/voice/upload-recording -> S3 upload, recording URI on PhoneCall

Assertions:
  PhoneCall.call_id matches throughout
  Conversation.status transitions: ACTIVE -> CLOSED (not ACTIVE -> orphaned)
  All messages belong to correct conversation
```

---

#### S9 — Routine Execution Pipeline

```
Setup:
  World + Routine with 3 items + daily schedule

Flow:
  discover_routines_needing_executions() -> finds the schedule
  generate_executions() -> creates RoutineExecution records
  Submit responses for each item -> RoutineSubmission created
  Complete execution -> status=completed

Assertions:
  Execution count matches schedule frequency
  Each RoutineItemResponse belongs to correct execution
  Completed execution can't be re-submitted

Failure:
  regenerate_executions() is atomic — if item 2 of 3 fails, all roll back
```

---

#### S10 — Subscription Gating

*Feature blocked when not subscribed.*

```
Setup:
  Account with NO active subscription

Action:
  Attempt gated operation (e.g., create campaign, add phone number)
  Assert: 402/403

Then:
  Add subscription -> same action succeeds

Then:
  Expire subscription -> same action -> 402/403 again
```

---

### II.B — Fixture Architecture

The existing `db_session` fixture leaks commits — proven by the `cleanup_tos_acceptances` workaround. SAVEPOINT-based rollback is the #1 infrastructure fix.

#### The SAVEPOINT Pattern

```python
@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine(TEST_DB_URL)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()

@pytest.fixture  # function-scoped
def db_session(db_engine):
    connection = db_engine.connect()
    transaction = connection.begin()                     # outer — never commits
    nested = connection.begin_nested()                   # SAVEPOINT
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    yield session

    session.close()
    transaction.rollback()                               # undoes everything, including commits
    connection.close()
```

When tested code calls `session.commit()`, it hits the SAVEPOINT, not the real transaction. The outer `transaction.rollback()` always wins. **This eliminates all `cleanup_*` fixtures.**

#### The Async Variant (required for streaming tests)

```python
@pytest.fixture
async def async_session(async_engine):
    async with async_engine.connect() as conn:
        trans = await conn.begin()
        await conn.begin_nested()
        session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint")
        yield session
        await session.close()
        await trans.rollback()
```

#### The `make_world()` Builder

```python
@dataclass
class World:
    account: Account
    project: Project
    agent: Agent
    user: User

def make_world(session, **overrides) -> World:
    account = make_account(session, **(overrides.get("account") or {}))
    agent = make_agent(session, account_id=account.id, **(overrides.get("agent") or {}))
    project = make_project(
        session, account_id=account.id, agent_id=agent.id,
        **(overrides.get("project") or {})
    )
    user = make_user(session, account_id=account.id, **(overrides.get("user") or {}))
    session.flush()  # get IDs without committing
    return World(account, project, agent, user)
```

Rule: sensible defaults, override only what the test cares about. A test about Stripe webhooks doesn't care what the agent's persona is.

#### The `httpx.AsyncClient` Fixture (required for SSE)

```python
@pytest.fixture
async def client(app_with_overrides):
    async with AsyncClient(
        transport=ASGITransport(app=app_with_overrides),
        base_url="http://test",
    ) as c:
        yield c
```

`TestClient` is synchronous — it cannot consume SSE streams. `httpx.AsyncClient` with ASGI transport is non-negotiable for scenarios S2, S3, S7, S8.

#### Auth Override (DI, not patching)

```python
def auth_as(account_id: UUID, role: str = "owner") -> UserContext:
    return UserContext(
        username=uuid4(), email="test@test.com",
        role=role, groups=[], display_name="Test"
    )

@pytest.fixture
def app_with_overrides(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_db_async] = async_session_yielder(db_session)
    app.dependency_overrides[authenticate_user] = lambda: auth_as(account_id)
    yield app
    app.dependency_overrides.clear()
```

#### Autouse Pool Health Check (catches ADR-019 regressions automatically)

```python
@pytest.fixture(autouse=True)
def assert_pool_healthy(db_engine):
    before = db_engine.pool.checkedout()
    yield
    after = db_engine.pool.checkedout()
    assert before == after, f"DB connection leak: {before} -> {after} checked out"
```

Fires on every test. If a streaming endpoint leaks a connection, you know immediately.

#### Scoping Rules

- `session`-scoped: DB engine, schema creation only
- `function`-scoped (default): everything else — each test gets a fresh `World` via `make_world(db_session)`
- **NEVER** use `session`-scoped fixtures for mutable data — one mutated Account causes 40 dependent test failures with no obvious cause.

---

### II.C — System Invariants

Properties that must hold always, across all tests. Not individual test cases — parameterized assertions across every entity type.

| Invariant | Assertion |
|-----------|-----------|
| **Tenant isolation** | `query(entity, acct=A) INTERSECT query(entity, acct=B) = empty set` for all entities |
| **Cross-tenant returns 404, not 403** | Don't leak resource existence |
| **Project-scoped conversation history** | Agent for Project A never sees Project B's messages |
| **Tool credential scoping** | Tool for Project A uses Project A's integration credentials |
| **RBAC denial is atomic** | 403 response AND DB state unchanged (no partial writes) |
| **Webhook idempotency** | `deliver(event) . deliver(event) == deliver(event)` |
| **Stream completeness** | Every started stream ends with `[DONE]` or error event — never silent truncation |
| **Pool health** | `pool.checkedout()` before == after, for every request (autouse fixture) |
| **Referential integrity** | Delete parent -> no orphaned children (app-enforced, ADR-004) |
| **Conversation lifecycle** | Status transitions are one-way: ACTIVE -> {INACTIVE, CLOSING, EXPIRED} -> CLOSED |

---

### II.D — Failure Injection

Where integration tests earn their keep. Ordered by production impact.

| Priority | Failure | Inject How | Assert What |
|----------|---------|-----------|-------------|
| **P0** | DB session leak mid-stream | Patch `AsyncSessionLocal` to raise after N commits | `pool.checkedout() == 0`, error event in SSE |
| **P0** | LLM timeout after first token | Mock SDK `create` to yield 1 chunk then `TimeoutError` | No partial message record in DB, conversation not stuck |
| **P1** | POS API 500 during tool call | Mock httpx response with 500 | Agent graceful degradation, no conversation corruption |
| **P1** | Webhook before record exists | POST `subscription.updated` before `subscription.created` | No 500, handled gracefully |
| **P2** | Concurrent conversation close | Two simultaneous `atomic_close_conversation()` | Exactly one succeeds (`rowcount == 1`), other gets 0 |
| **P2** | Auth token expired mid-request | Override auth to raise `HTTPException(401)` after DI resolves | No partial DB writes |
| **P3** | S3 upload failure during recording | Mock boto3 `put_object` to raise | PhoneCall record not corrupted, error logged |

**Injection rule**: mock at the HTTP/SDK boundary (not the service boundary) so error handling code runs for real.

---

## Part III: Unit Tests (20% of effort)

Mechanical. Each takes minutes to design.

| What | Why Unit | Pattern |
|------|----------|---------|
| Pydantic schemas (`api/schemas/`) | Pure validation, no side effects | `parametrize` with valid/invalid inputs |
| Agent prompt construction (`agent/input_output.py`) | Pure string building | Assert XML structure |
| Business hours calculation (`monitoring_service`) | Pure time/timezone math | `parametrize` with edge cases |
| Status machine transitions | Pure enum logic | Assert valid/invalid transitions |
| Phone number normalization | Pure parsing | `parametrize` with formats |
| URL extraction/filtering | Pure regex | `parametrize` with URLs |
| Event `to_detail()` serialization | Pure data transform | Assert UUID->str, datetime->ISO |
| Tool parameter validation | Pure Pydantic models | `parametrize` with valid/invalid |

No further design effort needed. Write them as you encounter the code.

---

## Part IV: Implementation Sequence

| Day | What | Why First |
|-----|------|-----------|
| **0** | Fix SAVEPOINT pattern in conftest. Delete all `cleanup_*` fixtures. Add pool-health autouse. | Unblocks everything. |
| **0** | Build `factories.py` with `make_world()`, `make_conversation()`, `make_message()`, `make_integration()`. | Unblocks all scenarios. |
| **0** | Build `httpx.AsyncClient` fixture with ASGI transport + auth DI override. | Unblocks streaming tests. |
| **1** | **S1** (tenant isolation) — parametrized across all entity types. | Proves the core safety property. |
| **1** | **S2** (streaming lifecycle) — happy path + mid-stream failure + client disconnect. | Prevents ADR-019 regression. |
| **2** | **S3** (full chat flow) + **S4** (RBAC zero side effects). | Core happy path + auth correctness. |
| **2** | **S5** (Stripe idempotency). | Financial correctness. |
| **3+** | S6-S10 in priority order. | Expanding scenario coverage. |

---

## Part V: Anti-Patterns

| Temptation | Why It's Wrong |
|-----------|---------------|
| "Add integration tests for every CRUD endpoint" | That's unit tests with a real DB. Integration tests are *scenarios*, not endpoint assertions. |
| "Mock repos in service integration tests" | If you mock your own code, you're back to testing call sequences. |
| "Use `TestClient` for streaming" | It's synchronous. SSE events buffer then deliver — you can't test streaming behavior. |
| "Session-scoped fixtures for mutable data" | One mutated Account causes 40 cascading failures. Function-scoped only. |
| "Write `cleanup_*` fixtures" | If you need cleanup, your SAVEPOINT rollback is broken. Fix the fixture, not the symptom. |
| "Get coverage to 90% first" | Coverage != confidence. 10 well-designed scenarios catch more production bugs than 200 mock-heavy endpoint tests. |

---

## Appendix A: Current State Numbers

| Layer | Source Files | Test Files | Test Functions | File Coverage |
|-------|------------|-----------|----------------|---------------|
| API routes | 67 | 25 | 409 | 37% |
| Services | 140 | 35 | 592 | 25% |
| DB repositories | 42 | 7 | 216 | 17% |
| Tools | 77 | 2 | 87 | 3% |
| Agent | 20 | 0 | 0 | 0% |
| Events | 2 | 1 | 14 | 50% |
| Utils | 4 | 1 | 5 | 25% |
| MCP | 2 | 1 | 6 | 50% |
| **TOTAL** | **~400** | **83** | **1,345** | **~21%** |

- 98% mock-heavy unit tests
- 1 real integration test file (TOS acceptance)
- 0 FastAPI TestClient-based API tests
- 0 end-to-end tests
- No shared factories or fixture library
- Coverage enforcement: 80% incremental only, 0% absolute floor

---

## Appendix B: ADR Constraints on Testing

| ADR | Constraint |
|-----|-----------|
| 002 (Layered arch) | Tests must not violate API->Service->DB; `lint-imports` enforces |
| 003 (Repository pattern) | All DB access through repos — mock repos in unit tests, real repos in integration |
| 004 (No FK constraints) | Can't rely on DB cascade — must test app-level referential integrity |
| 005 (Tools bypass services) | Tool tests mock repos directly (not services); test credential isolation |
| 015 (Cognito + RBAC) | Always mock Cognito; test RBAC with real DB tables |
| 017 (No ORM relationships) | No lazy loading — all joins explicit; test actual SQL behavior |
| 019 (Streaming session) | Streaming generators own session via `AsyncSessionLocal()`, not `Depends()` |

---

## Appendix C: Coverage Strategy

### Short-term

| Metric | Current | Target | Enforcement |
|--------|---------|--------|-------------|
| Absolute coverage floor | 0% | 40% | `fail_under = 40` in pyproject.toml |
| Incremental coverage (PRs) | 80% | 80% | Already enforced by diff-cover |

### Medium-term (3 months)

Ratchet absolute floor up 5% per sprint. Target: 60%.

### Long-term (6 months)

Target: 75% absolute floor. All 10 scenarios implemented.

### Test Pipeline Tiers

```
Tier 1: Pre-commit / local (< 30s)
  - @pytest.mark.smoke — factory/fixture health, schema validation, pure functions

Tier 2: PR to main (< 5min)
  - All unit tests + integration tests (PostgreSQL service container)
  - diff-cover 80% incremental gate
  - Absolute coverage floor gate

Tier 3: Nightly (< 30min)
  - @pytest.mark.slow — concurrency tests, full CRUD matrix
  - External API smoke tests (RUN_EXTERNAL_TESTS=1, Stripe sandbox, etc.)
```
