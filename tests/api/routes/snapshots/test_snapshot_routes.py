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


class TestComputeDiff:
    """Tests for POST /v1/snapshots:computeDiff."""

    DIFF_URL = f"{SNAPSHOTS_PREFIX}:computeDiff"

    @patch(
        "api.routes.snapshots._implementation.compute_snapshot_diff",
        new_callable=AsyncMock,
    )
    def test_compute_diff_returns_200_with_changes(self, mock_diff: AsyncMock) -> None:
        from_fp = "a" * 64
        to_fp = "b" * 64
        mock_diff.return_value = {
            "from_fingerprint": from_fp,
            "to_fingerprint": to_fp,
            "prompt_changed": True,
            "config_changed": True,
            "prompt_diff": "--- from_prompt\n+++ to_prompt\n@@ -1 +1 @@\n-old\n+new\n",
            "config_diff": [{"path": "model", "from": "gpt-4", "to": "gpt-4o"}],
        }

        response = client.post(
            self.DIFF_URL,
            json={"from_fingerprint": from_fp, "to_fingerprint": to_fp},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["from_fingerprint"] == from_fp
        assert data["to_fingerprint"] == to_fp
        assert data["prompt_changed"] is True
        assert data["config_changed"] is True
        assert "--- from_prompt" in data["prompt_diff"]
        assert len(data["config_diff"]) == 1
        assert data["config_diff"][0]["path"] == "model"

    @patch(
        "api.routes.snapshots._implementation.compute_snapshot_diff",
        new_callable=AsyncMock,
    )
    def test_compute_diff_identical_snapshots(self, mock_diff: AsyncMock) -> None:
        fp = "a" * 64
        mock_diff.return_value = {
            "from_fingerprint": fp,
            "to_fingerprint": fp,
            "prompt_changed": False,
            "config_changed": False,
            "prompt_diff": "",
            "config_diff": [],
        }

        response = client.post(
            self.DIFF_URL,
            json={"from_fingerprint": fp, "to_fingerprint": fp},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["prompt_changed"] is False
        assert data["config_changed"] is False
        assert data["prompt_diff"] == ""
        assert data["config_diff"] == []

    @patch(
        "api.routes.snapshots._implementation.compute_snapshot_diff",
        new_callable=AsyncMock,
    )
    def test_compute_diff_from_not_found_returns_404(
        self, mock_diff: AsyncMock
    ) -> None:
        from_fp = "c" * 64
        mock_diff.side_effect = ValueError(
            f"Snapshot with fingerprint '{from_fp}' not found"
        )

        response = client.post(
            self.DIFF_URL,
            json={"from_fingerprint": from_fp, "to_fingerprint": "d" * 64},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert from_fp in response.json()["detail"]

    @patch(
        "api.routes.snapshots._implementation.compute_snapshot_diff",
        new_callable=AsyncMock,
    )
    def test_compute_diff_to_not_found_returns_404(self, mock_diff: AsyncMock) -> None:
        to_fp = "d" * 64
        mock_diff.side_effect = ValueError(
            f"Snapshot with fingerprint '{to_fp}' not found"
        )

        response = client.post(
            self.DIFF_URL,
            json={"from_fingerprint": "c" * 64, "to_fingerprint": to_fp},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert to_fp in response.json()["detail"]

    @patch(
        "api.routes.snapshots._implementation.compute_snapshot_diff",
        new_callable=AsyncMock,
    )
    def test_compute_diff_response_has_all_fields(self, mock_diff: AsyncMock) -> None:
        mock_diff.return_value = {
            "from_fingerprint": "a" * 64,
            "to_fingerprint": "b" * 64,
            "prompt_changed": False,
            "config_changed": False,
            "prompt_diff": "",
            "config_diff": [],
        }

        response = client.post(
            self.DIFF_URL,
            json={"from_fingerprint": "a" * 64, "to_fingerprint": "b" * 64},
        )

        assert response.status_code == status.HTTP_200_OK
        expected_fields = {
            "from_fingerprint",
            "to_fingerprint",
            "prompt_changed",
            "config_changed",
            "prompt_diff",
            "config_diff",
        }
        assert set(response.json().keys()) == expected_fields
