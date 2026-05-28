"""Tests for admin analytics report route handlers."""

import datetime
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.routes.admin import _analytics as analytics_routes
from api.routes.admin import get_account_reports, get_reports
from api.schemas.admin.analytics import GetAllReportsResponse


def _make_response() -> GetAllReportsResponse:
    return GetAllReportsResponse(reports=[])


@pytest.mark.asyncio
async def test_get_reports_delegates_to_company_reports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _make_response()
    mock_get_company_reports = AsyncMock(return_value=response)
    monkeypatch.setattr(
        analytics_routes,
        "get_company_reports",
        mock_get_company_reports,
    )

    context = MagicMock()
    session = MagicMock()
    start_date = datetime.datetime(2026, 5, 1, tzinfo=datetime.UTC)
    end_date = datetime.datetime(2026, 5, 28, tzinfo=datetime.UTC)

    result = await get_reports(
        start_date=start_date,
        end_date=end_date,
        context=context,
        session=session,
        group_by=["account_id"],
    )

    assert result is response
    mock_get_company_reports.assert_awaited_once_with(
        context,
        session,
        start_date,
        end_date,
        group_by=["account_id"],
    )


@pytest.mark.asyncio
async def test_get_account_reports_delegates_to_account_reports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _make_response()
    mock_get_accounts_reports = AsyncMock(return_value=response)
    monkeypatch.setattr(
        analytics_routes,
        "get_accounts_reports",
        mock_get_accounts_reports,
    )

    context = MagicMock()
    session = MagicMock()
    start_date = datetime.datetime(2026, 5, 1, tzinfo=datetime.UTC)
    end_date = datetime.datetime(2026, 5, 28, tzinfo=datetime.UTC)
    project_id = uuid.uuid4()

    result = await get_account_reports(
        account_name="bobs-pizza",
        start_date=start_date,
        end_date=end_date,
        group_by=["project_id"],
        project_ids=[project_id],
        context=context,
        session=session,
    )

    assert result is response
    mock_get_accounts_reports.assert_awaited_once_with(
        "bobs-pizza",
        context,
        session,
        start_date,
        end_date,
        group_by=["project_id"],
        filter_by={"project_id": [project_id]},
    )
