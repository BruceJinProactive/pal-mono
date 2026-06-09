"""Tests for internal project endpoints."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status
from starlette.responses import Response

from api.routes.internal.projects import get_signal_source_by_camera_id
from api.schemas.operations.signal_source import SignalSourceIdResponse


@pytest.mark.asyncio
async def test_get_signal_source_by_camera_id_returns_source_id() -> None:
    """Return the signal source ID when the camera is configured."""
    project_id = uuid.uuid4()
    source_id = uuid.uuid4()
    source = MagicMock()
    source.id = source_id
    session = AsyncMock()

    with patch(
        "api.routes.internal.projects.signal_source_service.get_source_by_camera_id",
        new_callable=AsyncMock,
        return_value=source,
    ) as mock_get_source:
        result = await get_signal_source_by_camera_id(
            project_id=str(project_id),
            camera_id="camera-123",
            session=session,
        )

    assert isinstance(result, SignalSourceIdResponse)
    assert result.signal_source_id == source_id
    mock_get_source.assert_awaited_once_with(
        session=session,
        project_id=project_id,
        camera_id="camera-123",
    )


@pytest.mark.asyncio
async def test_get_signal_source_by_camera_id_skips_missing_source() -> None:
    """Return 204 so processors can skip unconfigured cameras."""
    with patch(
        "api.routes.internal.projects.signal_source_service.get_source_by_camera_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = await get_signal_source_by_camera_id(
            project_id=str(uuid.uuid4()),
            camera_id="unconfigured-camera",
            session=AsyncMock(),
        )

    assert isinstance(result, Response)
    assert result.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.asyncio
async def test_get_signal_source_by_camera_id_rejects_invalid_project_id() -> None:
    """Keep malformed project IDs as client errors."""
    with pytest.raises(HTTPException) as exc_info:
        await get_signal_source_by_camera_id(
            project_id="not-a-uuid",
            camera_id="camera-123",
            session=AsyncMock(),
        )

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
