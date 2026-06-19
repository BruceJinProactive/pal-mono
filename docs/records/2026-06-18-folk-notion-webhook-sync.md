# Folk Notion Webhook Sync

> **Date:** 2026-06-18

## Summary

Added a Folk to Notion webhook sync for the sales/FDE handoff workflow. The service listens for Folk deal create/update events, fetches the full deal plus linked company data, and creates or updates one Notion client page with deal-level and company-level fields.

## What Changed

- Added `POST /v1/integrations/folk/webhook` with Standard Webhooks signature verification.
- Added `services/folk_notion_sync/` for settings, Folk API reads, Notion data source writes, field mapping, retry handling, and Slack failure alerts.
- Scoped writes to Folk -> Notion only. Folk `object.deleted` events are acknowledged and ignored; no Notion pages are deleted or archived.
- Aggregates all current Pipeline Review deals for the same Folk company into one Notion client page.
- Uses the duplicate Notion database/data source created for the sync attempt, configured via `FOLK_NOTION_SYNC_NOTION_DATA_SOURCE_ID`.

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| Webhook-only MVP after historical sync | Historical Folk data was already manually synced into the duplicate Notion database, so the code path focuses on new and changed Folk entries. |
| One Notion page per company/client | Folk can have multiple deals per company, while the FDE workspace is organized around client pages. Deal IDs, URLs, stages, products, owners, and commercial fields are aggregated into Folk-prefixed properties. |
| No delete propagation | Sales/FDE cleanup should remain human-reviewed; a deleted Folk deal should not automatically remove or archive Notion context. |
| Feature flag disabled by default | Each environment can opt in only after secrets, Notion data source ID, Slack channel, and Folk webhook registration are ready. |

## Operational Notes

- Required secrets: `FOLK_API_KEY`, `NOTION_API_KEY`, `FOLK_WEBHOOK_SIGNING_SECRET`.
- Required env: `FOLK_NOTION_SYNC_ENABLED=true`, `FOLK_NOTION_SYNC_NOTION_DATA_SOURCE_ID=<notion-data-source-id>`.
- Optional env: `FOLK_NOTION_SYNC_SLACK_CHANNEL=<channel-name>`.
- Register Folk webhook events for `object.created` and `object.updated` on the Pipeline Review deals group. `object.deleted` can be subscribed safely, but the service ignores it.
