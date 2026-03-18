# Camera Health Monitoring v1

**Author:** Myroslav Vozniak
**Date:** 2026-03-18
**Status:** Approved

## Overview

Monitor camera health by tracking feed update activity. Health status is derived from `signal_feeds` table updates.

**Goals:**
- Camera health visibility based on feed activity
- Proactive detection of stale/failing cameras
- Simple Datadog dashboard for ops

---

## Architecture

```
┌────────────────────────────────────────┐
│   Camera Feed Updates                  │
│   • Video/image uploads                │
│   • Processor updates signal_feeds     │
│   • Emit metrics on each update        │
└────────────────┬───────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────┐
│   Datadog                              │
│   • Camera health metrics              │
│   • Alert on inactivity                │
│   • Dashboard visualization            │
└────────────────────────────────────────┘
```

---

## Health Status Logic

Camera health is derived from `signal_feeds.last_capture_at`:

```python
def get_camera_health_status(last_capture_at: datetime) -> str:
    """
    Determine camera health based on last feed update.

    Returns: 'active', 'inactive', or 'error'
    """
    if last_capture_at is None:
        return 'error'  # Never captured

    time_since_update = now() - last_capture_at

    if time_since_update < timedelta(minutes=5):
        return 'active'   # Recently updated
    elif time_since_update < timedelta(minutes=30):
        return 'inactive'  # Stale but not dead
    else:
        return 'error'     # Not updating, likely offline
```

**Status definitions:**
- `active`: Feed updated within last 5 minutes
- `inactive`: No update for 5-30 minutes (warning)
- `error`: No update for >30 minutes (critical)

---

## Metrics

Emit metrics when processing feed updates:

```python
# On each feed update
statsd.increment('camera.feed.updated', tags=[
    f'camera_id:{camera_id}',
    f'project_id:{project_id}',
    f'source_id:{source_id}'
])

# On feed processing errors
statsd.increment('camera.feed.error', tags=[
    f'camera_id:{camera_id}',
    f'error_type:{error_type}'  # upload_failed/processing_failed/invalid_format
])
```

### Metric Definitions

```
camera.feed.updated (counter, timestamp tracked by Datadog)
  tags: camera_id, project_id, source_id

camera.feed.error (counter)
  tags: camera_id, project_id, error_type
```

**Staleness detection:** Datadog automatically tracks the timestamp of the last `camera.feed.updated` event per camera. Alerts and dashboards query "time since last event" without needing gauge metrics.

---

## Datadog Dashboard

**Name:** "Camera Health Monitoring"

**Widgets:**

1. **Feed Update Rate**
   - Timeseries: `sum:camera.feed.updated` per minute
   - Shows overall system activity

2. **Active Cameras Count**
   - Query: Count distinct `camera_id` with events in last 5 minutes
   - Formula: `count(camera.feed.updated{*} by {camera_id}.rollup(count, 300))`

3. **Stale Cameras**
   - Query: Cameras with no events in last 5 minutes
   - Use Datadog monitor query: "No data in 5 minutes for camera_id"

4. **Time Since Last Update**
   - Timeseries: "Last seen" timestamp per camera
   - Use Datadog event timeline with `camera.feed.updated` events

5. **Error Breakdown**
   - Top List: `sum:camera.feed.error` by `error_type`
   - Identify common failure patterns

6. **Camera Activity Heatmap**
   - Heatmap: `camera.feed.updated` by `camera_id` over time
   - Visualize update patterns and gaps

---

## Alerts

### Critical Alerts

| Alert | Condition | Action |
|-------|-----------|--------|
| Camera Offline | No `camera.feed.updated` for camera_id in 30 min | SMS ops team |
| Mass Failure | >3 cameras with no data in 30 min | Page on-call |
| System Down | No `camera.feed.updated` events at all in 10 min | Page on-call |

### Warning Alerts

| Alert | Condition | Action |
|-------|-----------|--------|
| Camera Inactive | No `camera.feed.updated` for camera_id in 5 min | Slack #ops |
| High Error Rate | `camera.feed.error` rate > 10/min | Slack #ops |

---

## Data Model

Uses existing `signal_sources` and `signal_feeds` tables.

**Key fields:**
- `signal_sources.config['camera_id']`: Camera identifier
- `signal_feeds.last_capture_at`: Timestamp of last feed update
- `signal_feeds.error_log`: Recent errors (optional)

**Query for stale cameras:**
```sql
SELECT
  config->>'camera_id' as camera_id,
  project_id,
  last_capture_at,
  EXTRACT(EPOCH FROM (NOW() - last_capture_at)) as seconds_since_update
FROM signal_feeds
WHERE last_capture_at < NOW() - INTERVAL '5 minutes'
ORDER BY last_capture_at ASC;
```

---

## Implementation

### Code Changes

Add metrics to existing feed update handler:

```python
# In feed processing code (e.g., video/image upload endpoint)
async def update_signal_feed(camera_id, project_id, ...):
    try:
        # Update feed
        await feed_repo.update_last_capture(...)

        # Emit success metric
        statsd.increment('camera.feed.updated', tags=[
            f'camera_id:{camera_id}',
            f'project_id:{project_id}'
        ])
    except Exception as e:
        # Emit error metric
        statsd.increment('camera.feed.error', tags=[
            f'camera_id:{camera_id}',
            f'error_type:{type(e).__name__}'
        ])
        raise
```

**That's it!** No scheduled tasks, no workers, no cron jobs. Datadog tracks timestamps automatically.

### Rollout

1. Add 2 metric lines to existing feed update code
2. Deploy to LAT
3. Create Datadog dashboard using event timestamps
4. Configure "no data" alerts
5. Monitor for 1 week
6. Deploy to production

---

## Success Criteria

- ✅ Dashboard shows real-time camera status
- ✅ Alert triggers within 5 min of camera going inactive
- ✅ Zero false positives (cameras marked offline when active)
- ✅ Ops can identify problematic cameras quickly
