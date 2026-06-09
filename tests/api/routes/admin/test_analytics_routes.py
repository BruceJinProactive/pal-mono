"""Tests for admin analytics report route handlers."""

import datetime
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from api.routes.admin import _analytics as analytics_routes
from api.routes.admin import (
    admin_router,
    get_account_ordering_metrics,
    get_account_reports,
    get_reports,
)
from api.schemas.admin.analytics import GetAllReportsResponse
from api.schemas.admin.ordering_metrics import (
    OrderingMetricsResponse,
    OrderingMetricSummary,
)


def _make_response() -> GetAllReportsResponse:
    return GetAllReportsResponse(reports=[])


def _make_ordering_response() -> OrderingMetricsResponse:
    return OrderingMetricsResponse(
        account_name="bobs-pizza",
        ordering_enabled=True,
        period_start="2026-05-01",
        period_end="2026-05-02",
        time_series=[],
        summary=OrderingMetricSummary(
            total_orders=0,
            total_order_value=0.0,
            order_accuracy=None,
            order_call_count=0,
            accurate_order_call_count=0,
            tool_error_order_call_count=0,
        ),
    )


def test_company_reports_route_is_not_nested_under_accounts() -> None:
    paths = {route.path for route in admin_router.routes if isinstance(route, APIRoute)}

    assert "/admin/reports" in paths
    assert "/admin/accounts/reports" not in paths


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


@pytest.mark.asyncio
async def test_get_account_ordering_metrics_route_delegates_to_analytics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _make_ordering_response()
    mock_get_account_ordering_metrics = AsyncMock(return_value=response)
    monkeypatch.setattr(
        analytics_routes,
        "get_account_ordering_metrics",
        mock_get_account_ordering_metrics,
    )

    context = MagicMock()
    session = MagicMock()
    start_date = datetime.datetime(2026, 5, 1, tzinfo=datetime.UTC)
    end_date = datetime.datetime(2026, 5, 2, tzinfo=datetime.UTC)
    project_id = uuid.uuid4()

    result = await get_account_ordering_metrics(
        account_name="bobs-pizza",
        start_date=start_date,
        end_date=end_date,
        project_ids=[project_id],
        context=context,
        session=session,
    )

    assert result is response
    mock_get_account_ordering_metrics.assert_awaited_once_with(
        account_name="bobs-pizza",
        context=context,
        session=session,
        start_date=start_date,
        end_date=end_date,
        project_ids=[project_id],
    )


@pytest.mark.asyncio
async def test_analytics_get_account_ordering_metrics_delegates_to_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account_id = uuid.uuid4()
    account = MagicMock()
    account.id = account_id
    response = _make_ordering_response()
    mock_get_account = MagicMock(return_value=account)
    mock_get_ordering_metrics = AsyncMock(return_value=response)
    monkeypatch.setattr(analytics_routes, "get_account", mock_get_account)
    monkeypatch.setattr(
        analytics_routes,
        "get_ordering_metrics",
        mock_get_ordering_metrics,
    )

    context = MagicMock()
    session = MagicMock()
    start_date = datetime.datetime(2026, 5, 1, tzinfo=datetime.UTC)
    end_date = datetime.datetime(2026, 5, 2, tzinfo=datetime.UTC)
    project_id = uuid.uuid4()

    result = await analytics_routes.get_account_ordering_metrics(
        account_name="bobs-pizza",
        context=context,
        session=session,
        start_date=start_date,
        end_date=end_date,
        project_ids=[project_id],
    )

    assert result is response
    mock_get_account.assert_called_once_with(session, "bobs-pizza")
    mock_get_ordering_metrics.assert_awaited_once_with(
        session=session,
        account_id=account_id,
        account_name="bobs-pizza",
        start_date=start_date,
        end_date=end_date,
        project_ids=[project_id],
    )


@pytest.mark.asyncio
async def test_analytics_get_account_ordering_metrics_raises_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(analytics_routes, "get_account", MagicMock(return_value=None))

    with pytest.raises(HTTPException) as exc_info:
        await analytics_routes.get_account_ordering_metrics(
            account_name="missing-account",
            context=MagicMock(),
            session=MagicMock(),
        )

    assert exc_info.value.status_code == 404
