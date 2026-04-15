# Tags API Usage

Tags are sent as a **JSON string** in `multipart/form-data`.

## Create

`POST /v1/projects/{project_id}/monitoring/configs`

| Field | Value |
|-------|-------|
| `tags` | `["Food consistency", "Cleanliness"]` |

> Omit `tags` to default to `[]`.

## Update

`PATCH /v1/projects/{project_id}/monitoring/configs/{config_id}`

Full-list replacement — send the entire desired list.

### Add a tag

Before: `["Food consistency", "Cleanliness"]`

| Field | Value |
|-------|-------|
| `tags` | `["Food consistency", "Cleanliness", "Wait time"]` |

After: `["Food consistency", "Cleanliness", "Wait time"]`

### Remove a tag

Before: `["Food consistency", "Cleanliness", "Wait time"]`

| Field | Value |
|-------|-------|
| `tags` | `["Food consistency", "Wait time"]` |

After: `["Food consistency", "Wait time"]`

### Rename a tag

Before: `["Food consistency", "Cleanliness"]`

| Field | Value |
|-------|-------|
| `tags` | `["Food consistency", "Kitchen cleanliness"]` |

After: `["Food consistency", "Kitchen cleanliness"]`

### Clear all

| Field | Value |
|-------|-------|
| `tags` | `[]` |

### No change

Omit `tags` field entirely.

## Get

`GET /v1/projects/{project_id}/monitoring/configs/{config_id}`

```json
{ "tags": ["Food consistency", "Cleanliness"] }
```

## Delete

`DELETE /v1/projects/{project_id}/monitoring/configs/{config_id}` — tags removed with config.

## Summary

`GET /v1/projects/{project_id}/monitoring/summary?start_date=2026-04-14&end_date=2026-04-15`

```json
{
  "project_name": "Downtown Location",
  "total_tags": 2,
  "tags": [
    { "tag": "Food consistency", "total_runs": 50, "pass_count": 40, "fail_count": 8, "error_count": 2, "fail_rate": 0.16 },
    { "tag": "Cleanliness", "total_runs": 30, "pass_count": 28, "fail_count": 2, "error_count": 0, "fail_rate": 0.0667 }
  ]
}
```

Defaults to today. `end_date` is exclusive. Only configs with non-empty tags appear.
