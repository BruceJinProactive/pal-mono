"""Tests for _get_project_timezone helper in operation routes."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api.routes.operation import _get_project_timezone


class TestGetProjectTimezone:
    async def test_returns_project_timezone(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()

        mock_project = MagicMock()
        mock_project.timezone = "America/New_York"

        with patch("api.routes.operation.ProjectRepository") as mock_repo_cls:
            mock_repo_cls.return_value.get_by_id = AsyncMock(return_value=mock_project)
            result = await _get_project_timezone(project_id, session)

        assert result == "America/New_York"
        mock_repo_cls.return_value.get_by_id.assert_awaited_once_with(project_id)

    async def test_raises_404_when_project_not_found(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()

        with patch("api.routes.operation.ProjectRepository") as mock_repo_cls:
            mock_repo_cls.return_value.get_by_id = AsyncMock(return_value=None)

            with pytest.raises(HTTPException) as exc_info:
                await _get_project_timezone(project_id, session)

        assert exc_info.value.status_code == 404

    async def test_falls_back_to_la_when_timezone_none(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()

        mock_project = MagicMock()
        mock_project.timezone = None

        with patch("api.routes.operation.ProjectRepository") as mock_repo_cls:
            mock_repo_cls.return_value.get_by_id = AsyncMock(return_value=mock_project)
            result = await _get_project_timezone(project_id, session)

        assert result == "America/Los_Angeles"

    async def test_falls_back_to_la_when_timezone_invalid(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()

        mock_project = MagicMock()
        mock_project.timezone = "Invalid/Timezone"

        with patch("api.routes.operation.ProjectRepository") as mock_repo_cls:
            mock_repo_cls.return_value.get_by_id = AsyncMock(return_value=mock_project)
            result = await _get_project_timezone(project_id, session)

        assert result == "America/Los_Angeles"
