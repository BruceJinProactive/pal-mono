# Tool Result Storage With AWS ElastiCache

**Last updated:** 2026-06-02

This doc describes how tool-call results could be stored in AWS ElastiCache so
multiple `pal-mono` pods can share recent tool outputs across turns.

## AWS Setup

Use ElastiCache for Valkey or Redis OSS, preferably in the same VPC/subnets as
the API pods.

Required AWS pieces:

- ElastiCache serverless cache or replication group.
- Security group allowing the API pods to connect to the cache port.
- TLS enabled for production.
- Authentication using one of:
  - Redis/Valkey username and password stored in AWS Secrets Manager.
  - IAM authentication for Valkey 7.2+ or Redis OSS 7+, with TLS enabled.
- CloudWatch alarms for connection count, CPU, memory, evictions, and errors.

Boto3 can create, describe, and manage ElastiCache resources, but application
data access still uses a Redis/Valkey client such as `redis-py`.

## App Dependency

Add the Redis Python client:

```toml
"redis>=5,<7"
```

Use `redis.asyncio.Redis` for the async `pal-mono` request path. For cluster
mode, use the Redis cluster client instead of the single-endpoint client.

## Configuration

Add environment variables such as:

```text
REDIS_CACHE_ENABLED=true
REDIS_CACHE_HOST=...
REDIS_CACHE_PORT=6379
REDIS_CACHE_USERNAME=...
REDIS_CACHE_AUTH_MODE=secrets_manager
REDIS_CACHE_SECRET_KEY=REDIS_CACHE_AUTH_TOKEN
REDIS_CACHE_SSL=true
REDIS_CACHE_DEFAULT_TTL_SECONDS=1800
REDIS_CACHE_MAX_ITEM_BYTES=32768
REDIS_CACHE_SOCKET_CONNECT_TIMEOUT_SECONDS=2.0
REDIS_CACHE_SOCKET_TIMEOUT_SECONDS=2.0
REDIS_CACHE_HEALTH_CHECK_INTERVAL_SECONDS=30
```

These Redis cache settings are intentionally not tool-result-specific so other
cache-backed features can reuse the same ElastiCache client. For
`REDIS_CACHE_AUTH_MODE=secrets_manager`, `REDIS_CACHE_SECRET_KEY` is the key
name looked up through the existing AWS Secrets Manager helper, with an
environment variable fallback for local development. Store the Redis/Valkey auth
token under that key in deployed environments; do not put the raw password in
deployment config.

For `REDIS_CACHE_AUTH_MODE=iam`, keep TLS enabled and use an IAM
auth-token provider instead of a static password. The IAM path requires Valkey
7.2+ or Redis OSS 7+ and should be wired when the runtime adapter starts using
IAM auth.

## Data Model

Use one Redis list per conversation:

```text
tool-results:v1:{conversation_id}
```

Each list item is compact JSON:

```json
{
  "tool_name": "toast_takeout_create_order_v1",
  "input_summary": "Create a takeout order for the selected cart",
  "result_summary": "Order was created and is pending payment.",
  "cacheable_result": {
    "status": "success",
    "order_state": "pending_payment"
  },
  "status": "success",
  "error_type": null,
  "captured_at": "2026-05-27T15:30:00Z"
}
```

The cache entry should include a result that is useful to the next-turn prompt.
Prefer a short `result_summary` plus allowlisted structured fields over a raw
tool payload. `input_summary` is optional; include it only when the sanitized
tool input adds meaningful context that is not already in chat history.

Only cache explicitly allowlisted fields. Do not cache raw tool responses
verbatim. The cache writer must redact or drop secrets, auth tokens, payment
details, customer contact PII, addresses, free-form notes, and any integration
payload fields that are not needed for the next-turn prompt.

Do not inject the full cache item into the model context. The cache item may
carry metadata for storage/debugging, but prompt rendering should strip it down
to the same compact shape used by the current cache:

```json
{"tool_name":"toast_takeout_create_order_v1","tool_result":{"status":"success","order_state":"pending_payment"}}
```

If no compact structured result is available, use the sanitized result summary:

```json
{"tool_name":"toast_takeout_create_order_v1","tool_result":"Order was created and is pending payment."}
```

Keep the list ephemeral:

- `RPUSH` new result.
- `EXPIRE` the key for `REDIS_CACHE_DEFAULT_TTL_SECONDS`.

Do not trim the list by count by default. Long ordering conversations may need
early tool results later in the same conversation. Rely on TTL for expiry and on
per-item byte limits plus monitoring to control memory use.

## Write Path

`pal-agents` already emits `tool_call` events. `pal-mono` can write those events
to ElastiCache from both message paths:

- Non-streaming: after `pal_agent.run(pal_input)` returns events.
- Streaming: when an empty-content chunk carries `events`.

Writes should be best-effort and should not block the user response. If Redis is
unavailable, log a warning/metric and continue.

Example write shape:

```python
cacheable_payload = build_cacheable_tool_result(payload)
if cacheable_payload is None:
    return

entry = json.dumps(cacheable_payload, ensure_ascii=True, separators=(",", ":"))
key = f"tool-results:v1:{conversation_id}"

async with redis.pipeline(transaction=True) as pipe:
    pipe.rpush(key, entry)
    pipe.expire(key, ttl_seconds)
    await pipe.execute()
```

## Read Path

Before each `PalAgent.run(...)`, `pal-mono` reads:

```python
items = await redis.lrange(f"tool-results:v1:{conversation_id}", 0, -1)
previous_tool_results = [json.loads(item) for item in items]
```

Before those results are injected into prompt context, strip cache-only fields
such as `captured_at`, `status`, `error_type`, and `input_summary` unless a
specific tool needs a sanitized input summary. The default context item should
contain only `tool_name` and `tool_result`.

Then pass the parsed list into `pal-agents`, either as:

- a new `PalInput.previous_tool_results` field, or
- an extra `RuntimeContext.previous_tool_results` field.

`pal-agents` should render those values into the existing
`<previous_tool_results>` prompt block. During rollout, `pal-agents` can prefer
externally supplied results and fall back to its current in-memory cache.

## Connection Management

Create a single async Redis client/pool per process and reuse it across
requests. Close it on application shutdown.

Recommended client settings:

- TLS enabled with `ssl=True`.
- `decode_responses=True`.
- finite socket/connect timeouts.
- health checks on idle connections.
- bounded connection pool size.

## Rollout

1. Provision ElastiCache and network access.
2. Add Redis client dependency and cache config.
3. Add a small shared cache adapter, e.g. `utils/cache/redis.py`.
4. Dual-write: keep the current in-memory cache and also write ElastiCache.
5. Read ElastiCache results before agent runs and compare with local cache.
6. Switch `pal-agents` to prefer externally supplied results.
7. Remove the process-local cache once cross-pod behavior is verified.

## Important Limits

ElastiCache is not durable storage. It is good for recent turn context, but not
for audit trails, eval history, or analytics that must survive eviction or cache
replacement.

Large tool results can consume memory and inflate prompts. Keep a max byte
limit and store only cacheable fields. If a future use case needs large or
sensitive payloads, store a pointer to durable storage and apply that storage
layer's redaction/retention policy instead of putting the payload directly in
ElastiCache.

Because the list is not trimmed by count, memory alarms and payload byte limits
matter. If production data shows runaway lists within the TTL window, add a
conversation-level byte cap or tool-specific compression/summarization before
reintroducing count-based trimming.

## References

- AWS ElastiCache Python guide:
[https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/ElastiCache-Getting-Started-Tutorials-Python.html](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/ElastiCache-Getting-Started-Tutorials-Python.html)
- Boto3 ElastiCache client reference:
[https://docs.aws.amazon.com/boto3/latest/reference/services/elasticache.html](https://docs.aws.amazon.com/boto3/latest/reference/services/elasticache.html)
- ElastiCache IAM authentication:
[https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/auth-iam.html](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/auth-iam.html)
- ElastiCache connection guidance:
[https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/BestPractices.Clients.Redis.Connections.html](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/BestPractices.Clients.Redis.Connections.html)
