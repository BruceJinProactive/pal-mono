"""Tests for snapshot API routes."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import status
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

SNAPSHOTS_PREFIX = "/v1/snapshots"


def _make_mock_snapshot(
    fingerprint: str = "a" * 64,
    agent_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
) -> MagicMock:
    snapshot = MagicMock()
    snapshot.fingerprint = fingerprint
    snapshot.agent_id = agent_id or uuid.uuid4()
    snapshot.project_id = project_id or uuid.uuid4()
    snapshot.system_prompt_hash = "b" * 64
    snapshot.system_prompt_text = "You are a helpful restaurant assistant."
    snapshot.config_snapshot = {"model": "gpt-4", "temperature": 0.7}
    snapshot.first_seen_at = datetime.now(timezone.utc)
    snapshot.last_seen_at = datetime.now(timezone.utc)
    return snapshot


class TestGetSnapshot:
    """Tests for GET /v1/snapshots/{fingerprint}."""

    @patch(
        "api.routes.snapshots._implementation.get_snapshot_by_fingerprint",
        new_callable=AsyncMock,
    )
    def test_get_snapshot_returns_200(self, mock_get: AsyncMock) -> None:
        fingerprint = "a" * 64
        mock_snapshot = _make_mock_snapshot(fingerprint=fingerprint)
        mock_get.return_value = mock_snapshot

        response = client.get(f"{SNAPSHOTS_PREFIX}/{fingerprint}")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["fingerprint"] == fingerprint
        assert data["system_prompt_text"] == "You are a helpful restaurant assistant."
        assert data["config_snapshot"] == {"model": "gpt-4", "temperature": 0.7}
        assert data["agent_id"] == str(mock_snapshot.agent_id)
        assert data["project_id"] == str(mock_snapshot.project_id)

    @patch(
        "api.routes.snapshots._implementation.get_snapshot_by_fingerprint",
        new_callable=AsyncMock,
    )
    def test_get_snapshot_not_found_returns_404(self, mock_get: AsyncMock) -> None:
        mock_get.return_value = None
        fingerprint = "c" * 64

        response = client.get(f"{SNAPSHOTS_PREFIX}/{fingerprint}")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"]

    @patch(
        "api.routes.snapshots._implementation.get_snapshot_by_fingerprint",
        new_callable=AsyncMock,
    )
    def test_get_snapshot_response_has_all_fields(self, mock_get: AsyncMock) -> None:
        mock_snapshot = _make_mock_snapshot()
        mock_get.return_value = mock_snapshot

        response = client.get(f"{SNAPSHOTS_PREFIX}/{'a' * 64}")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        expected_fields = {
            "fingerprint",
            "agent_id",
            "project_id",
            "system_prompt_hash",
            "system_prompt_text",
            "config_snapshot",
            "first_seen_at",
            "last_seen_at",
        }
        assert set(data.keys()) == expected_fields
