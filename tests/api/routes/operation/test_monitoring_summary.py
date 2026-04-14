"""Tests for monitoring summary route handler.

Covers get_monitoring_summary handler error mapping and success path.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

# Import the router-level function for coverage of __init__.py lines
from api.routes.operation import get_monitoring_summary as router_get_monitoring_summary
from api.routes.operation._monitoring import get_monitoring_summary
from api.schemas.operations.monitoring import MonitoringSummaryResponse


class TestGetMonitoringSummaryHandler:
    """Tests for the route handler layer."""

    @pytest.mark.asyncio
    async def test_success_returns_response(self) -> None:
        """Handler returns MonitoringSummaryResponse on success."""
        project_id = uuid.uuid4()
        expected = MonitoringSummaryResponse(
            project_id=project_id,
            project_name="Test",
            total_tags=0,
            start_date=None,
            end_date=None,
            tags=[],
        )

        with patch(
            "api.routes.operation._monitoring.monitoring_service"
        ) as mock_service:
            mock_service.get_monitoring_summary = AsyncMock(return_value=expected)

            result = await get_monitoring_summary(
                session=AsyncMock(),
                project_id=project_id,
            )

        assert result == expected

    @pytest.mark.asyncio
    async def test_project_not_found_raises_404(self) -> None:
        """Handler maps ValueError to 404."""
        with patch(
            "api.routes.operation._monitoring.monitoring_service"
        ) as mock_service:
            mock_service.get_monitoring_summary = AsyncMock(
                side_effect=ValueError("Project not found")
            )

            with pytest.raises(HTTPException) as exc_info:
                await get_monitoring_summary(
                    session=AsyncMock(),
                    project_id=uuid.uuid4(),
                )

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_unexpected_error_raises_500(self) -> None:
        """Handler maps unexpected exceptions to 500."""
        with patch(
            "api.routes.operation._monitoring.monitoring_service"
        ) as mock_service:
            mock_service.get_monitoring_summary = AsyncMock(
                side_effect=RuntimeError("DB down")
            )

            with pytest.raises(HTTPException) as exc_info:
                await get_monitoring_summary(
                    session=AsyncMock(),
                    project_id=uuid.uuid4(),
                )

        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_forwards_date_params(self) -> None:
        """Handler passes start_date and end_date to service."""
        project_id = uuid.uuid4()
        start = datetime(2026, 4, 1, tzinfo=timezone.utc)
        end = datetime(2026, 4, 14, tzinfo=timezone.utc)
        session = AsyncMock()

        expected = MonitoringSummaryResponse(
            project_id=project_id,
            project_name="Test",
            total_tags=0,
            start_date=start,
            end_date=end,
            tags=[],
        )

        with patch(
            "api.routes.operation._monitoring.monitoring_service"
        ) as mock_service:
            mock_service.get_monitoring_summary = AsyncMock(return_value=expected)

            await get_monitoring_summary(
                session=session,
                project_id=project_id,
                start_date=start,
                end_date=end,
            )

            mock_service.get_monitoring_summary.assert_called_once_with(
                session=session,
                project_id=project_id,
                start_date=start,
                end_date=end,
            )

    @pytest.mark.asyncio
    async def test_router_endpoint_delegates_to_handler(self) -> None:
        """Router-level function delegates to _monitoring handler."""
        project_id = uuid.uuid4()
        expected = MonitoringSummaryResponse(
            project_id=project_id,
            project_name="Router Test",
            total_tags=0,
            start_date=None,
            end_date=None,
            tags=[],
        )

        with patch(
            "api.routes.operation._monitoring.monitoring_service"
        ) as mock_service:
            mock_service.get_monitoring_summary = AsyncMock(return_value=expected)

            result = await router_get_monitoring_summary(
                project_id=project_id,
                context=MagicMock(),
                session=AsyncMock(),
            )

        assert result == expected
