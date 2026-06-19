from __future__ import annotations

from functools import lru_cache
from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class FolkNotionSyncSettings(BaseSettings):
    """Environment-backed settings for the Folk to Notion webhook sync."""

    model_config = SettingsConfigDict(
        env_prefix="FOLK_NOTION_SYNC_",
        extra="ignore",
    )

    enabled: bool = False
    folk_base_url: str = "https://api.folk.app"
    folk_group_id: str = "grp_3454c312-a64a-47c7-af0c-098c5fa9e9f9"
    folk_object_type: str = "Deals"
    notion_base_url: str = "https://api.notion.com"
    notion_data_source_id: str = ""
    notion_version: str = "2026-03-11"
    slack_channel_env_key: str = "FOLK_NOTION_SYNC_SLACK_CHANNEL"
    request_timeout_seconds: float = Field(default=20.0, gt=0)
    max_retries: int = Field(default=3, ge=0)

    @model_validator(mode="after")
    def validate_enabled_settings(self) -> Self:
        if self.enabled and not self.notion_data_source_id:
            raise ValueError(
                "FOLK_NOTION_SYNC_NOTION_DATA_SOURCE_ID is required when enabled"
            )
        return self


@lru_cache(maxsize=1)
def get_folk_notion_sync_settings() -> FolkNotionSyncSettings:
    return FolkNotionSyncSettings()
