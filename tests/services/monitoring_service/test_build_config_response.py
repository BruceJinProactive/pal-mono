"""Tests for monitoring service build_config_response.

Covers the parallel presigning logic for reference images:
- Successful presigning
- Fallback when map_uri_to_s3_url returns empty string
- Fallback when map_uri_to_s3_url raises an exception
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


def _make_config(rules: dict | None = None) -> MagicMock:
    config = MagicMock()
    config.id = uuid.uuid4()
    config.project_id = uuid.uuid4()
    config.signal_source_id = uuid.uuid4()
    config.name = "test-config"
    config.description = None
    config.rules = rules or {}
    config.enabled = True
    config.created_at = datetime.now(tz=timezone.utc)
    config.updated_at = None
    return config


class TestBuildConfigResponse:
    """Unit tests for monitoring_service.build_config_response."""

    @pytest.mark.asyncio
    async def test_presigns_reference_image_urls(self) -> None:
        """Images with URLs are presigned via map_uri_to_s3_url."""
        config = _make_config(
            rules={
                "reference_images": [
                    {"url": "s3://bucket/img1.jpg"},
                    {"url": "s3://bucket/img2.jpg"},
                ]
            }
        )

        with patch(
            "services.monitoring_service._implementation.map_uri_to_s3_url",
            side_effect=lambda url: f"https://presigned/{url}",
        ):
            from services.monitoring_service._implementation import (
                build_config_response,
            )

            resp = await build_config_response(config)

        assert (
            resp.rules["reference_images"][0]["url"]
            == "https://presigned/s3://bucket/img1.jpg"
        )
        assert (
            resp.rules["reference_images"][1]["url"]
            == "https://presigned/s3://bucket/img2.jpg"
        )

    @pytest.mark.asyncio
    async def test_preserves_url_when_presign_returns_empty(self) -> None:
        """Falls back to original URL when map_uri_to_s3_url returns empty string."""
        config = _make_config(
            rules={"reference_images": [{"url": "s3://bucket/img.jpg"}]}
        )

        with patch(
            "services.monitoring_service._implementation.map_uri_to_s3_url",
            return_value="",
        ):
            from services.monitoring_service._implementation import (
                build_config_response,
            )

            resp = await build_config_response(config)

        assert resp.rules["reference_images"][0]["url"] == "s3://bucket/img.jpg"

    @pytest.mark.asyncio
    async def test_preserves_url_when_presign_raises(self) -> None:
        """Falls back to original URL when map_uri_to_s3_url raises an exception."""
        config = _make_config(
            rules={"reference_images": [{"url": "s3://bucket/img.jpg"}]}
        )

        with patch(
            "services.monitoring_service._implementation.map_uri_to_s3_url",
            side_effect=RuntimeError("S3 error"),
        ):
            from services.monitoring_service._implementation import (
                build_config_response,
            )

            resp = await build_config_response(config)

        assert resp.rules["reference_images"][0]["url"] == "s3://bucket/img.jpg"

    @pytest.mark.asyncio
    async def test_skips_images_without_url(self) -> None:
        """Images without a url key are not presigned."""
        config = _make_config(
            rules={
                "reference_images": [
                    {"url": "s3://bucket/img.jpg"},
                    {"description": "no url here"},
                ]
            }
        )

        with patch(
            "services.monitoring_service._implementation.map_uri_to_s3_url",
            return_value="https://presigned/img.jpg",
        ) as mock_presign:
            from services.monitoring_service._implementation import (
                build_config_response,
            )

            resp = await build_config_response(config)

        mock_presign.assert_called_once()
        assert resp.rules["reference_images"][0]["url"] == "https://presigned/img.jpg"
        assert resp.rules["reference_images"][1] == {"description": "no url here"}
