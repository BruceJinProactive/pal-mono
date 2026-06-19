from __future__ import annotations

from services import slack_service
from services.folk_notion_sync._settings import FolkNotionSyncSettings
from utils.log import logger


async def send_sync_failure_alert(
    settings: FolkNotionSyncSettings,
    *,
    title: str,
    detail: str,
    event_id: str,
    event_type: str,
) -> None:
    channel = slack_service.get_slack_channel_from_env_key(
        settings.slack_channel_env_key
    )
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Folk -> Notion sync failed*\n*{title}*",
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Event*\n{event_type}"},
                {"type": "mrkdwn", "text": f"*Event ID*\n{event_id}"},
            ],
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"```{detail[:2500]}```"},
        },
    ]
    try:
        result = await slack_service.send_slack_message(
            blocks,
            channel,
            text_fallback=f"Folk -> Notion sync failed: {title}",
        )
        if result.get("status") != "success":
            logger.error(
                "[FolkNotionSync] Slack alert send returned error",
                extra={
                    "event_id": event_id,
                    "event_type": event_type,
                    "channel": channel,
                    "result": result,
                },
            )
    except Exception:
        logger.exception("[FolkNotionSync] Failed to send Slack alert")
