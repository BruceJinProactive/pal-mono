import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

import db
from api.routes.endpoints import endpoints
from api.schemas.error.error import ErrorResponse
from services.analytics_service.schema import CallInsightsResponse
from services.auth_service import require_account_permission
from services.auth_types import UserContext

from . import _analytics
from ._auth import authenticate_user

call_insights_router = APIRouter()


@call_insights_router.get(
    endpoints.ADMIN_ACCOUNT_CALL_INSIGHTS,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
def get_account_call_insights(
    account_name: str,
    start_date: datetime | None = Query(
        default=None,
        description="Start date for call insights. If not provided, defaults to 7 days ago.",
    ),
    end_date: datetime | None = Query(
        default=None,
        description="End date for call insights. If not provided, defaults to today.",
    ),
    project_ids: list[uuid.UUID] | None = Query(
        default=None,
        description="Optional list of project IDs to filter call insights by.",
    ),
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> CallInsightsResponse:
    """
    Retrieve call-level business review insights for this account.
    """
    return _analytics.get_account_call_insights(
        account_name=account_name,
        context=context,
        session=session,
        start_date=start_date,
        end_date=end_date,
        project_ids=project_ids,
    )
