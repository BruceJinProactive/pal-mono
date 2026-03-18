# ADR-019: Streaming Endpoints Must Own Their DB Session

**Date:** 2026-03-18
**Status:** Accepted
**Context:** DB connection pool leak investigation (March 2026)

## Context

After deploying LiveKit voice integration (March 2), every streaming request through `POST /chat/completions` and `POST /chat` leaked exactly one database connection. The leak was caused by the interaction between three components:

1. **`BaseHTTPMiddleware`** (added Feb 20 in `api/middleware.py`) — wraps request handling such that the endpoint runs in a subtask. When the handler returns a `StreamingResponse` object, FastAPI's dependency cleanup fires immediately — before the response body is consumed.

2. **`Depends(db.get_db_async)`** — the standard FastAPI dependency that provides an `AsyncSession`. Its cleanup (`finally: await db.close()`) runs when the handler returns, not when streaming completes.

3. **`StreamingResponse(generate())`** — the generator closure captures the `session` from `Depends`, but that session is already closed by the time the generator starts yielding chunks.

This meant every streaming request checked out a connection that was closed prematurely by dependency cleanup, then abandoned by the generator. The GC eventually reclaimed these as "non-checked-in connections."

The leak was invisible before March 2 because no streaming traffic flowed through these endpoints until LiveKit voice calls started using `POST /chat/completions`.

## Decision

**Streaming endpoints must manage their own `AsyncSessionLocal()` inside the generator function, not rely on `Depends(get_db_async)`.**

The generator owns the full session lifecycle:

```python
@router.post("/stream")
async def stream_endpoint(request: StreamRequest):
    # Do NOT use Depends(get_db_async) for the streaming session

    async def generate() -> AsyncIterator[str]:
        async with AsyncSessionLocal() as session:
            try:
                stream = await get_stream(session=session, ...)
                async for chunk in stream:
                    yield f"data: {json.dumps(chunk)}\n\n"
                await session.commit()
            except Exception:
                await session.rollback()
                raise
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

Non-streaming parameters (authentication, request validation) can still use `Depends()` since they complete before the handler returns.

## Consequences

### Positive
- Eliminates the 1:1 connection leak per streaming request
- Session lifetime exactly matches the streaming lifetime
- Works correctly regardless of middleware stack (`BaseHTTPMiddleware`, Starlette middleware, etc.)

### Negative
- Streaming endpoints deviate from the standard `Depends(get_db_async)` pattern used elsewhere
- Developers must know when to use which pattern (streaming vs non-streaming)

### Mitigations
- `api/routes/CLAUDE.md` documents the streaming session pattern with a warning about the `Depends` incompatibility
- The postmortem and this ADR explain the root cause so future developers understand *why*

## Affected Files

- `api/routes/chat/chat_completions.py` — `chat_completions_agno` streaming endpoint
- `api/routes/chat/chat.py` — `chat` streaming endpoint (`stream=True` path)

## References

- `docs/records/2026-03-17-db-connection-leak-fixes.md`
- `docs/records/2026-03-06-db-pool-exhaustion-postmortem.md`
- [Starlette BaseHTTPMiddleware streaming behavior](https://github.com/encode/starlette/issues/1012)
- [SQLAlchemy async session docs](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
