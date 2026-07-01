import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from api.schemas.admin.analytics import GetAllReportsResponse
from api.schemas.admin.ordering_metrics import OrderingMetricsResponse
from api.schemas.admin.ordering_revenue_metrics import OrderingRevenueMetricsResponse

from . import _implementation
from .schema import CallInsightsResponse


async def get_reports(
    session: Session,
    account_id: uuid.UUID | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    group_by: list[str] | None = None,
    filter_by: dict[str, uuid.UUID | list[uuid.UUID]] | None = None,
) -> GetAllReportsResponse:
    """
    Get all analytics reports for a given account within a date range.
    This is the main analytics function.

    Args:
        session (Session): Database session
        account_id (uuid.UUID): The account ID to calculate analytics for
        start_date (datetime | None): Start date for the calculation
        end_date (datetime | None): End date for the calculation
        group_by (list[str] | None): List of fields to group by
        filter_by (dict): Filter parameters

    Returns:
        GetAllReportsResponse: Object containing all analytics reports
    """
    return await _implementation.get_reports(
        session,
        account_id,
        start_date,
        end_date,
        group_by=group_by,
        filter_by=filter_by,
    )


async def get_account_reports(
    session: Session,
    account_id: uuid.UUID,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    group_by: list[str] | None = None,
    filter_by: dict[str, uuid.UUID | list[uuid.UUID]] | None = None,
) -> GetAllReportsResponse:
    """
    Wrapper function for backward compatibility. Calls get_reports internally.

    Args:
        session (Session): Database session
        account_id (uuid.UUID): The account ID to calculate analytics for
        start_date (datetime): Start date for the calculation
        end_date (datetime): End date for the calculation
        group_by (list[str] | None): List of fields to group by
        filter_by (dict): Filter parameters

    Returns:
        GetAllReportsResponse: Object containing all analytics reports
    """
    return await get_reports(
        session,
        account_id,
        start_date,
        end_date,
        group_by=group_by,
        filter_by=filter_by,
    )


async def get_ordering_metrics(
    session: Session,
    account_id: uuid.UUID,
    account_name: str,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    project_ids: list[uuid.UUID] | None = None,
) -> OrderingMetricsResponse:
    """
    Get ordering dashboard metrics for an account/project scope.

    Args:
        session: Database session
        account_id: Account ID
        account_name: Account name for the response
        start_date: Optional start date
        end_date: Optional end date
        project_ids: Optional project filter

    Returns:
        OrderingMetricsResponse: Capability gate plus time-series metrics
    """
    return await _implementation.get_ordering_metrics(
        session=session,
        account_id=account_id,
        account_name=account_name,
        start_date=start_date,
        end_date=end_date,
        project_ids=project_ids,
    )


async def get_ordering_revenue_metrics(
    session: Session,
    account_id: uuid.UUID,
    account_name: str,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    project_ids: list[uuid.UUID] | None = None,
) -> OrderingRevenueMetricsResponse:
    """
    Get ordering revenue dashboard metrics for an account/project scope.
    """
    return await _implementation.get_ordering_revenue_metrics(
        session=session,
        account_id=account_id,
        account_name=account_name,
        start_date=start_date,
        end_date=end_date,
        project_ids=project_ids,
    )


def get_call_insights(
    session: Session,
    account_id: uuid.UUID,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    project_ids: list[uuid.UUID] | None = None,
) -> CallInsightsResponse:
    """Get call-level business review metrics for an account/project scope."""
    return _implementation.get_call_insights(
        session=session,
        account_id=account_id,
        start_date=start_date,
        end_date=end_date,
        project_ids=project_ids,
    )
