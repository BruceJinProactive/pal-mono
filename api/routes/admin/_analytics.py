from fastapi import Request
from sqlalchemy.orm import Session

from api.schemas.admin.analytics import PerformanceReport
from services import analytics_service
from services.analytics_service import get_report_from_mixpanel

from . import _auth


def get_report(
    request: Request,
    report_name: str,
    session: Session,
) -> dict | None:
    """
    Fetches insights data from Mixpanel for a given report name and account.

    Args:
        request (Request): The FastAPI request object containing the headers with the authorization token.
        report_name (str): The name of the report to fetch data for.
        session (Session): The SQLAlchemy session for database access.

    Returns:
        dict | None: The report data from Mixpanel.
    """
    account = _auth.get_account_from_id_token(request, session)
    account_name = account.name
    return get_report_from_mixpanel(report_name, account_name)


def get_all_reports(
    account_name: str,
) -> list[PerformanceReport]:
    """
    Fetches all insights data from Mixpanel for all reports defined in BOOKMARK_ID_MAPPING.

    Args:
        account_name (str): The name of the account to fetch data for.

    Returns:
        list[PerformanceReport]: A list of reports
    """
    reports = analytics_service.get_all_reports_from_mixpanel(account_name)
    return [PerformanceReport(name=name, data=data) for name, data in reports]
