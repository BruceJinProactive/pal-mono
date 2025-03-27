from fastapi import Request
from sqlalchemy.orm import Session

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
