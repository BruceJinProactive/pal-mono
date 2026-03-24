# Integration Test Infrastructure & Scenario Tests (S1-S10)

**Date:** 2026-03-23
**PR:** #3783
**Plans:** `docs/plans/testing-strategy/` (14 plans, all completed)

## Summary

Implemented the full integration-first testing strategy: Phase 0 infrastructure (SAVEPOINT fixtures, factory library, async client, coverage tiers) plus 10 scenario tests covering the critical paths identified in the testing strategy overview.

## What Changed

### Phase 0: Infrastructure

- **SAVEPOINT fixture** (`tests/integration/conftest.py`): `db_session` uses `join_transaction_mode="create_savepoint"` so `session.commit()` hits a SAVEPOINT. Outer `transaction.rollback()` undoes everything — no cleanup fixtures needed. Async variant uses `event.listens_for("after_transaction_end")` to restart nested transactions.
- **Factory library** (`tests/factories.py`): 20+ factories with sensible defaults. `make_world()` creates Account+Agent+Project+User in one call. Override only what the test cares about.
- **Async client** (`conftest.py`): `httpx.AsyncClient` with `ASGITransport` for SSE streaming tests. DI overrides for `get_db`, `get_db_async`, `authenticate_user`, `require_admin`.
- **Pool-health autouse fixture**: Checks `pool.checkedout()` before/after every test to catch DB connection leaks (ADR-019).
- **Coverage tiers**: `fail_under=20` (target 40), `--strict-markers`, nightly CI workflow for `@pytest.mark.slow` tests.

### Scenario Tests (74 test cases total)

| Scenario | File | Tests | What it proves |
|----------|------|-------|----------------|
| S1 Tenant Isolation | `test_tenant_isolation.py` | 11 | Every tenant-scoped repo method returns only queried tenant's data |
| S2 Streaming Lifecycle | `test_streaming_lifecycle.py` | 4 | SSE [DONE] terminator, [ERROR] on failure, ADR-019 compliance |
| S3 First Conversation | `test_s3_first_conversation.py` | 8 | Conversation creation, status transitions (ACTIVE/EXPIRED/INACTIVE), JSONB round-trip |
| S4 RBAC | `test_s4_rbac.py` | 7 | Role assignments, cross-tenant isolation, AccountUser membership |
| S5 Stripe Webhook | `test_s5_stripe_webhook.py` | 9 | Idempotent status updates, out-of-order delivery, payment lifecycle |
| S6 POS Credentials | `test_pos_credential_isolation.py` | 6 | Per-project credential scoping, secret_key isolation |
| S7 Cross-Project | `test_cross_project_conversation_isolation.py` | 3 | Conversation/message set disjointness across projects |
| S8 Voice Lifecycle | `test_voice_call_lifecycle.py` | 7 | VoiceConfig + PhoneCall creation, call_id lookup, chain integrity |
| S9 Routine Pipeline | `test_routine_execution_pipeline.py` | 8 | Routine→Item→Schedule→Execution→Submission hierarchy, status transitions |
| S10 Subscription Gating | `test_subscription_gating.py` | 11 | Active/expired/cancelled/trialing/pending states, overlap detection |

### Existing Test Cleanup

- Removed `cleanup_tos_acceptances` fixture from `test_tos_integration.py` (SAVEPOINT handles rollback automatically).

## Key Decisions

- **Mock at network/process boundary only**: LLM, S3, EventBridge, Stripe signature verification are mocked. Own code (repos, services) runs for real against PostgreSQL.
- **Sync repos for most tests**: Async repos tested via `async_session` fixture only where the plan specifically calls for it (S2 streaming).
- **Set-intersection invariant**: Multiple tests prove `query(entity, tenant=A) INTERSECT query(entity, tenant=B) = empty set`.

## Findings

The S1 tenant isolation exploration revealed several repository methods with no account_id guard on single-entity lookups:
- `ProjectRepository.get_project(project_id)` — no account_id filter
- `AgentRepository.get_agent(agent_id)` — no account_id filter
- `ConversationRepository.get_conversation_by_id()` — no account/project filter

Isolation for these methods relies on the service layer filtering first. Documented as a gap — not a blocker for this PR but worth hardening.
